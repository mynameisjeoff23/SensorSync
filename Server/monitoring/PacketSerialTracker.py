from dataclasses import dataclass

UINT32_MOD = 1 << 32
UINT32_MASK = UINT32_MOD - 1
UINT32_HALF_RANGE = 1 << 31

@dataclass
class PacketSerialTracker:
    last_serial: int | None = None
    received_packets: int = 0
    dropped_packets: int = 0

    def observe(self, packet_serial: int) -> None:
        packet_serial = packet_serial & UINT32_MASK

        if self.last_serial is None:
            self.last_serial = packet_serial
            self.received_packets += 1
            return

        delta = (packet_serial - self.last_serial) & UINT32_MASK

        if delta == 0:
            self.received_packets += 1
            return

        if delta <= UINT32_HALF_RANGE:
            if delta > 1:
                self.dropped_packets += delta - 1

            self.received_packets += 1
            self.last_serial = packet_serial
            return

        # A large backwards jump usually means a reconnect or sender reset.
        # Treat it as a new baseline instead of inventing a huge drop count.
        self.received_packets += 1
        self.last_serial = packet_serial