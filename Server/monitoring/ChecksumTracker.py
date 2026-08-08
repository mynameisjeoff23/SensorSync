import struct
from dataclasses import dataclass


@dataclass
class ChecksumTracker:
    successful_checksums: int = 0
    failed_checksums: int = 0

    @staticmethod
    def compute_header_checksum(magic: bytes, start_time: int, packet_serial: int, payload_len: int) -> int:
        """Compute a simple 16-bit checksum over header fields except checksum itself."""
        header_without_checksum = struct.pack("<4sIIH", magic, start_time, packet_serial, payload_len)
        return sum(header_without_checksum) & 0xFFFF

    def validate(self, magic: bytes, start_time: int, packet_serial: int, payload_len: int, received_checksum: int) -> bool:
        """Validate a received checksum and track the result.
        
        Args:
            magic: 4-byte magic value.
            start_time: Start time in microseconds.
            packet_serial: Packet serial number.
            payload_len: Payload length in bytes.
            received_checksum: The checksum value received in the header.
        
        Returns:
            True if the checksum is valid, False otherwise.
        """
        expected_checksum = self.compute_header_checksum(magic, start_time, packet_serial, payload_len)
        is_valid = received_checksum == expected_checksum
        
        if is_valid:
            self.successful_checksums += 1
        else:
            self.failed_checksums += 1
        
        return is_valid
