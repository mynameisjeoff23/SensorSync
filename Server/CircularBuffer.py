from collections import deque

class CircularBuffer:
    def __init__(self, capacity):
        self._capacity = capacity
        self._buffer = deque(maxlen=capacity)

    def add(self, item):
        self._buffer.append(item)

    def get(self):
        if not self.is_empty():
            return self._buffer.popleft() 
        else: 
            return None

    def size(self):
        return len(self._buffer)
    
    def is_full(self):
        return len(self._buffer) == self._capacity

    def is_empty(self):
        return len(self._buffer) == 0

    def clear(self):
        self._buffer.clear()