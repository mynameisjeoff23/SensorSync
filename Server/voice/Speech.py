import platform
import subprocess
import sys

class Speech:

    def __init__(self, printOut:bool=False):
        self.message = str()
        self.printOut = printOut

        if self.printOut:
            title = "Speech Output"
            os_name = platform.system()

            if os_name == 'Windows':
                # Open a dedicated console that only echoes speech text.
                relay_code = (
                    "import os, sys\n"
                    f"os.system('title {title}')\n"
                    "while True:\n"
                    "    chunk = sys.stdin.read(1)\n"
                    "    if not chunk:\n"
                    "        break\n"
                    "    sys.stdout.write(chunk)\n"
                    "    sys.stdout.flush()\n"
                )
                self.proc = subprocess.Popen(
                    [sys.executable, "-u", "-c", relay_code],
                    stdin=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )

            elif os_name == 'Darwin':  # macOS
                self.proc = subprocess.Popen([
                    'osascript',
                    '-e',
                    (
                        'tell application "Terminal" to do script "echo \''
                        f'{title}\'; cat"'
                    ),
                ],)

            else:  # Linux
                self.proc = subprocess.Popen(
                    ['gnome-terminal', '--', 'bash', '-c', 'cat'],
                    stdin=subprocess.PIPE,
                    text=True,
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
                    if self.proc and self.proc.stdin:
                        self.proc.stdin.write(new_words)
                        self.proc.stdin.flush()
        else:
            # If there is no common subsentence, print the entire new message
            if new:
                if self.printOut:
                    if self.proc and self.proc.stdin:
                        self.proc.stdin.write(new)
                        self.proc.stdin.flush()

        # Update the current message to the new message
        self.message = new

if __name__ == "__main__":
    print(f"{__file__} is not meant to be run as main")