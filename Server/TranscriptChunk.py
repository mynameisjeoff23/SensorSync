from collections import deque
import numpy as np
import numpy.typing as npt
import logging

FREQUENCY = 16000                                   # audio frequency in Hz
AUDIO_LENGTH_S = 5                                  # length of audio to keep in seconds
DEFAULT_SIZE_SAMPLES = FREQUENCY * AUDIO_LENGTH_S   # default size of transcript chunk in samples

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

class TranscriptChunk:

    def __init__(self, size:int=DEFAULT_SIZE_SAMPLES) -> None:
        """Creates a TranscriptChunk object. 
        This chunk is a circular buffer of bytes that represents the most recent audio received from the client. 
        The size of the chunk is determined by the size parameter, which is the number of samples to keep in the chunk. 
        The chunk is stored as a bytes object, and is updated with each new chunk of audio received from the client.

        Args:
            size (int): size of transcript buffer in samples
        """
        self.MAX_SIZE = DEFAULT_SIZE_SAMPLES * 4        # max size in bytes (4 bytes per sample for int32)
        self.chunks = bytearray()
        self.startIndex = 0


    def add(self, chunk: bytes) -> None:
        """Adds a chunk of audio to the transcript chunk. 

        Args:
            chunk (bytes): audio chunk to add
        """
        # TODO: make this circular using startIndex, good for now
        if len(chunk) >= self.MAX_SIZE:
            self.chunks = bytearray(chunk[-self.MAX_SIZE:])
            self.startIndex = 0
            return
    
        self.chunks.extend(chunk)
        excess = len(self.chunks) - self.MAX_SIZE
        if excess > 0:
            del self.chunks[:excess]


    def asFloat32(self) -> npt.NDArray[np.float32]:
        """ Returns the current transcript chunk as a numpy array of float32 values normalized to the range [-1.0, 1.0].

        Returns:
            npt.NDArray[np.float32]: _description_
        """
        # raw audio data is 24 bit, so normailization uses 8388608.0
        audio = np.frombuffer(self.chunks, dtype='<i4')
        normalized = audio.astype(np.float32) / 8388608.0
        maximum = np.max(np.abs(normalized))
        if maximum > 1.0:
            logger.warning("Audio normalization resulted in a value of %f, outside of [-1.0, 1.0]. Check input data.", maximum)
        return normalized

    def first20(self) -> bytes:
        """Returns the first 20 bytes of the transcript chunk. Used for debugging.

        Returns:
            bytes: first 20 bytes of the transcript chunk
        """
        return bytes(self.chunks[:20])

    def __len__(self) -> int:
        return len(self.chunks)


    def __bool__(self) -> bool:
        return len(self.chunks) > 0


    def getSize(self) -> int:
        """Returns the current size of the transcript chunk in bytes.

        Returns:
            int: size of the transcript chunk in bytes
        """
        return len(self.chunks)
