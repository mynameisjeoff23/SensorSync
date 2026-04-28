"""Stress test harness for Server/server.py.

This script connects to localhost, sends valid audio frames, intentionally malformed
headers/payloads, and simulates packet loss by skipping packet serial numbers.
"""

from __future__ import annotations

import argparse
import os
import random
import socket
import struct
import threading
import time
from dataclasses import dataclass


HOST = "127.0.0.1"
PORT = 8000
HEADER_FORMAT = "<4sIIHH"
MAX_PAYLOAD_LEN = 4096


@dataclass(frozen=True)
class StressConfig:
	host: str
	port: int
	clients: int
	sessions_per_client: int
	frames_per_session: int
	malformed_ratio: float
	fragment_chance: float
	serial_drop_every: int
	min_chunk_delay_ms: int
	max_chunk_delay_ms: int
	seed: int


def compute_header_checksum(magic: bytes, start_time_us: int, packet_serial: int, payload_len: int) -> int:
	start_time_us &= 0xFFFFFFFF
	packet_serial &= 0xFFFFFFFF
	payload_len &= 0xFFFF
	header_without_checksum = struct.pack("<4sIIH", magic, start_time_us, packet_serial, payload_len)
	return sum(header_without_checksum) & 0xFFFF


def build_header(magic: bytes, start_time_us: int, packet_serial: int, payload_len: int) -> bytes:
	start_time_us &= 0xFFFFFFFF
	packet_serial &= 0xFFFFFFFF
	payload_len &= 0xFFFF
	checksum = compute_header_checksum(magic, start_time_us, packet_serial, payload_len)
	return struct.pack(HEADER_FORMAT, magic, start_time_us, packet_serial, payload_len, checksum)


def build_valid_frame(start_time_us: int, packet_serial: int, payload_len: int) -> bytes:
	payload = os.urandom(payload_len)
	return build_header(b"AUD0", start_time_us, packet_serial, payload_len) + payload


def build_malformed_frame(rng: random.Random, start_time_us: int, packet_serial: int) -> bytes:
	payload_len = rng.choice([2, 6, 1022, 4097, 5000])
	payload = os.urandom(max(0, min(payload_len, MAX_PAYLOAD_LEN)))

	variant = rng.choice(["bad_magic", "bad_checksum", "bad_length", "truncated_header", "truncated_payload"])
	if variant == "bad_magic":
		header = build_header(b"BAD0", start_time_us, packet_serial, min(payload_len, MAX_PAYLOAD_LEN))
		return header + payload

	if variant == "bad_checksum":
		good_len = min(payload_len if payload_len <= MAX_PAYLOAD_LEN else 1024, MAX_PAYLOAD_LEN)
		header = bytearray(build_header(b"AUD0", start_time_us, packet_serial, good_len))
		header[-1] ^= 0xFF
		return bytes(header) + os.urandom(good_len)

	if variant == "bad_length":
		bad_len = payload_len if payload_len <= MAX_PAYLOAD_LEN else payload_len
		checksum = compute_header_checksum(b"AUD0", start_time_us, packet_serial, bad_len)
		header = struct.pack(HEADER_FORMAT, b"AUD0", start_time_us, packet_serial, bad_len, checksum)
		return header + payload

	if variant == "truncated_header":
		return build_header(b"AUD0", start_time_us, packet_serial, 1024)[:8]

	truncated = build_header(b"AUD0", start_time_us, packet_serial, 1024) + os.urandom(1024)
	return truncated[:-rng.randint(1, 32)]


def send_with_fragmentation(sock: socket.socket, payload: bytes, rng: random.Random, config: StressConfig) -> None:
	if len(payload) <= 1:
		sock.sendall(payload)
		return

	offset = 0
	while offset < len(payload):
		remaining = len(payload) - offset
		chunk_size = rng.randint(1, min(remaining, 128))
		sock.sendall(payload[offset:offset + chunk_size])
		offset += chunk_size

		if config.min_chunk_delay_ms or config.max_chunk_delay_ms:
			delay_ms = rng.randint(config.min_chunk_delay_ms, config.max_chunk_delay_ms)
			if delay_ms:
				time.sleep(delay_ms / 1000.0)


def send_frame(sock: socket.socket, frame: bytes, rng: random.Random, config: StressConfig) -> None:
	if rng.random() < config.fragment_chance:
		send_with_fragmentation(sock, frame, rng, config)
	else:
		sock.sendall(frame)


def run_session(client_id: int, session_id: int, config: StressConfig, seed_offset: int) -> None:
	rng = random.Random(config.seed + seed_offset)
	serial = 0  

	with socket.create_connection((config.host, config.port), timeout=5.0) as sock:
		sock.settimeout(5.0)
		for frame_index in range(config.frames_per_session):
			start_time_us = (time.time_ns() // 1000) & 0xFFFFFFFF
			use_malformed = rng.random() < config.malformed_ratio

			if use_malformed:
				frame = build_malformed_frame(rng, start_time_us, serial)
				send_frame(sock, frame, rng, config)
				break

			payload_len = rng.choice([256, 512, 1024, 2048, 4096])
			frame = build_valid_frame(start_time_us, serial, payload_len)
			send_frame(sock, frame, rng, config)

			serial += 1
			if config.serial_drop_every > 0 and (frame_index + 1) % config.serial_drop_every == 0:
				serial += 1

			if config.min_chunk_delay_ms or config.max_chunk_delay_ms:
				delay_ms = rng.randint(config.min_chunk_delay_ms, config.max_chunk_delay_ms)
				if delay_ms:
					time.sleep(delay_ms / 1000.0)


def worker(client_id: int, config: StressConfig) -> None:
	for session_id in range(config.sessions_per_client):
		try:
			run_session(client_id, session_id, config, seed_offset=client_id * 10_000 + session_id)
			print(f"client={client_id} session={session_id} completed")
		except (ConnectionRefusedError, TimeoutError, socket.timeout, BrokenPipeError, ConnectionResetError) as exc:
			print(f"client={client_id} session={session_id} failed: {exc}")
			time.sleep(0.1)


def parse_args() -> StressConfig:
	parser = argparse.ArgumentParser(description="Stress test for Server/server.py")
	parser.add_argument("--host", default=HOST)
	parser.add_argument("--port", type=int, default=PORT)
	parser.add_argument("--clients", type=int, default=4)
	parser.add_argument("--sessions-per-client", type=int, default=20)
	parser.add_argument("--frames-per-session", type=int, default=32)
	parser.add_argument("--malformed-ratio", type=float, default=0.15)
	parser.add_argument("--fragment-chance", type=float, default=0.75)
	parser.add_argument("--serial-drop-every", type=int, default=7)
	parser.add_argument("--min-chunk-delay-ms", type=int, default=0)
	parser.add_argument("--max-chunk-delay-ms", type=int, default=5)
	parser.add_argument("--seed", type=int, default=1337)
	args = parser.parse_args()

	if args.clients < 1:
		raise ValueError("--clients must be at least 1")
	if args.sessions_per_client < 1:
		raise ValueError("--sessions-per-client must be at least 1")
	if args.frames_per_session < 1:
		raise ValueError("--frames-per-session must be at least 1")
	if not 0.0 <= args.malformed_ratio <= 1.0:
		raise ValueError("--malformed-ratio must be between 0 and 1")
	if not 0.0 <= args.fragment_chance <= 1.0:
		raise ValueError("--fragment-chance must be between 0 and 1")
	if args.min_chunk_delay_ms < 0 or args.max_chunk_delay_ms < 0:
		raise ValueError("chunk delay values must be non-negative")
	if args.max_chunk_delay_ms < args.min_chunk_delay_ms:
		raise ValueError("--max-chunk-delay-ms must be >= --min-chunk-delay-ms")

	return StressConfig(
		host=args.host,
		port=args.port,
		clients=args.clients,
		sessions_per_client=args.sessions_per_client,
		frames_per_session=args.frames_per_session,
		malformed_ratio=args.malformed_ratio,
		fragment_chance=args.fragment_chance,
		serial_drop_every=args.serial_drop_every,
		min_chunk_delay_ms=args.min_chunk_delay_ms,
		max_chunk_delay_ms=args.max_chunk_delay_ms,
		seed=args.seed,
	)


def main() -> None:
	config = parse_args()
	threads = []

	print(
		f"Starting stress test against {config.host}:{config.port} with "
		f"{config.clients} clients, {config.sessions_per_client} sessions/client"
	)

	for client_id in range(config.clients):
		thread = threading.Thread(target=worker, args=(client_id, config), daemon=True)
		thread.start()
		threads.append(thread)

	for thread in threads:
		thread.join()

	print("Stress test completed")


if __name__ == "__main__":
	main()
