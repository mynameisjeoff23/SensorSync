import platform
import subprocess
import sys

class Speech:

    def __init__(self, printOut:bool=False):
        self.message = str()
        self.printOut = printOut

        if self.printOut:
            title = "Speech Output"
            system_name = platform.system()

            consumer_script = (
                "import sys; "
                "while True: "
                "    chunk = sys.stdin.read(1); "  # Read 1 character at a time
                "    if not chunk: break; "
                "    sys.stdout.write(chunk); "
                "    sys.stdout.flush()"
            )

            if system_name == "Windows":
                self.terminal = subprocess.Popen(
                    [sys.executable, '-c', consumer_script],
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=0,  # Turn off buffering to send characters instantly
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            elif system_name == "Darwin":
                # macOS requires a script approach to pipe into a specific new window
                # TODO: implement macOS solution
                raise NotImplementedError('macOS requires named pipes for stdin routing')
            else:
                # Linux: Launch a shell inside a new gnome-terminal
                self.terminal = subprocess.Popen(
                    [
                        'gnome-terminal',
                        '--',
                        sys.executable,
                        '-c',
                        consumer_script,
                    ],
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=0,
                )


    def longestCommonSubsentence(self, new:str) -> str:
        """
        Returns the longest common subsentence between the current message and a new message.

        Args:
            new (str): The new message to compare with the current message.

        Returns:
            str: The longest common subsentence.
        """
        # Split both messages into words
        words1 = self.message.split()
        words2 = new.split()

        # Create a 2D array to store lengths of longest common suffixes
        m, n = len(words1), len(words2)
        lcsuff = [[0] * (n + 1) for _ in range(m + 1)]
        length = 0  # Length of longest common subsentence
        end_index = 0  # End index of longest common subsentence in words1

        # Build the lcsuff table
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if words1[i - 1] == words2[j - 1]:
                    lcsuff[i][j] = lcsuff[i - 1][j - 1] + 1
                    if lcsuff[i][j] > length:
                        length = lcsuff[i][j]
                        end_index = i
                else:
                    lcsuff[i][j] = 0

        # Extract the longest common subsentence
        if length == 0:
            return ""
        
        start_index = end_index - length
        return ' '.join(words1[start_index:end_index])

    def searchKeywords(self):
        """Searches for keywords in the current message and performs actions based on them."""
        pass


    def addNewWords(self, new: str) -> None:
        """Takes old string and new string, finds longest common subsentence, and print the new words
        
        Args:
            new (str): The new message to compare with the current message.
        
        Returns:
            None
        """

        common_subsentence = self.longestCommonSubsentence(new)
        if common_subsentence:
            # Find the index of the common subsentence in the new message
            index = new.find(common_subsentence)
            # Print the new words that come after the common subsentence
            new_words = new[index + len(common_subsentence):].strip()
            if new_words:
                if self.printOut:
                    if self.terminal.poll() is None:
                        self.terminal.stdin.write(new_words)
                        self.terminal.stdin.flush()
        else:
            # If there is no common subsentence, print the entire new message
            if new:
                if self.printOut:
                    if self.terminal.poll() is None:
                        self.terminal.stdin.write(new)
                        self.terminal.stdin.flush()

        # Update the current message to the new message
        self.message = new