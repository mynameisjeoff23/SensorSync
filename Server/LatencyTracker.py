import time
from dataclasses import dataclass, field


@dataclass
class LatencyTracker:
    """Tracks packet latency by comparing packet headers timestamps with server reception time."""
    
    packets_observed: int = 0
    total_latency_us: int = 0
    min_latency_us: int | None = None
    max_latency_us: int | None = None
    last_latency_us: int | None = None
    negative_latency_count: int = 0  # Clock skew or out-of-order packets
    
    def observe(self, packet_start_time_us: int) -> None:
        """Record a packet's latency based on its header timestamp.
        
        Args:
            packet_start_time_us: The start_time_us field from the packet header (uint32, microseconds).
        """
        # Get current server time in microseconds
        current_time_us = int(time.time() * 1_000_000)
        
        # Compute latency (how long ago the packet was timestamped)
        latency_us = current_time_us - packet_start_time_us
        
        self.packets_observed += 1
        self.total_latency_us += latency_us
        self.last_latency_us = latency_us
        
        # Track negative latency (packet timestamp is in the future - clock skew)
        if latency_us < 0:
            self.negative_latency_count += 1
        
        # Update min/max only for positive latencies to avoid skewing statistics
        if latency_us >= 0:
            if self.min_latency_us is None or latency_us < self.min_latency_us:
                self.min_latency_us = latency_us
            if self.max_latency_us is None or latency_us > self.max_latency_us:
                self.max_latency_us = latency_us
    
    def average_latency_us(self) -> float:
        """Return the average latency in microseconds, or 0 if no packets observed."""
        if self.packets_observed == 0:
            return 0.0
        return self.total_latency_us / self.packets_observed
    
    def average_latency_ms(self) -> float:
        """Return the average latency in milliseconds."""
        return self.average_latency_us() / 1000.0
