import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional


class Speech:

    def __init__(self, printOut: bool = False, command_file: Optional[str | Path] = None):
        self.message = str()
        self.printOut = printOut
        self.proc = None
        self.command_file = Path(command_file) if command_file else Path(__file__).with_name("commands.txt")
        self.wakewords = []
        self.commands = []
        self.on_command: Optional[Callable[[dict], None]] = None
        self._command_lock_key: Optional[str] = None
        self._has_output_written = False
        self._load_commands()

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

    def _load_commands(self) -> None:
        if not self.command_file.exists():
            return

        self.wakewords = []
        self.commands = []
        current_section = None

        for raw_line in self.command_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            lowered = line.lower()
            if lowered.startswith("wakewords:"):
                self.wakewords = self._parse_alternatives(line.split(":", 1)[1])
                current_section = None
                continue

            if lowered.startswith("commands:"):
                current_section = "commands"
                continue

            if current_section != "commands":
                continue

            parsed = self._parse_command(line)
            if parsed is not None:
                self.commands.append(parsed)

        if not self.wakewords:
            self.wakewords = ["computa"]

    def _parse_alternatives(self, value: str) -> list[str]:
        return [token.strip() for token in value.split("/") if token.strip()]

    def _normalize_command_slot(self, slot: str) -> Optional[str]:
        slot_aliases = {
            "action": "verb",
            "target": "object",
            "detail": "modifier",
        }

        normalized = slot_aliases.get(slot.lower(), slot.lower())
        if normalized in {"verb", "object", "modifier"}:
            return normalized
        return None

    def _parse_labeled_command(self, line: str) -> Optional[dict]:
        slot_values = {
            "verb": [],
            "object": [],
            "modifier": [],
        }

        current_slot = None
        saw_labeled_slot = False

        for raw_token in line.split():
            token = raw_token.strip().rstrip(",")
            if not token:
                continue

            lowered = token.lower()
            if ":" in lowered or "=" in lowered:
                slot_name, value = re.split(r"[:=]", lowered, maxsplit=1)
                current_slot = self._normalize_command_slot(slot_name)
                if current_slot is None:
                    current_slot = None
                    continue

                saw_labeled_slot = True
                if value:
                    slot_values[current_slot].extend(self._parse_alternatives(value))
                    current_slot = None
                continue

            if current_slot is not None:
                slot_values[current_slot].extend(self._parse_alternatives(lowered))
                current_slot = None

        if not saw_labeled_slot:
            return None

        if not slot_values["verb"] or not slot_values["object"]:
            return None

        return {
            "verb": slot_values["verb"],
            "object": slot_values["object"],
            "modifier": slot_values["modifier"],
            "raw": line,
        }

    def _parse_command(self, line: str) -> Optional[dict]:
        labeled_command = self._parse_labeled_command(line)
        if labeled_command is not None:
            return labeled_command

        parts = [part.strip() for part in line.split() if part.strip()]
        if len(parts) < 2:
            return None

        return {
            "verb": self._parse_alternatives(parts[0]),
            "object": self._parse_alternatives(parts[1]),
            "modifier": self._parse_alternatives(parts[2]) if len(parts) > 2 else [],
            "raw": line,
        }

    def _transcript_tokens(self, text: str) -> list[tuple[str, int, int]]:
        tokens = []
        for match in re.finditer(r"[A-Za-z0-9%']+[^\w\s]*", text):
            normalized = match.group(0).lower().rstrip(".,!?;:\"')]}")
            if normalized:
                tokens.append((normalized, match.start(), match.end()))
        return tokens

    def _collapse_adjacent_duplicate_words(self, text: str) -> str:
        if not text:
            return ""

        tokens = self._transcript_tokens(text)
        if not tokens:
            return text.strip()

        pieces = []
        cursor = 0
        previous_word = None

        for word, start, end in tokens:
            if word == previous_word:
                cursor = end
                continue

            pieces.append(text[cursor:start])
            pieces.append(text[start:end])
            cursor = end
            previous_word = word

        pieces.append(text[cursor:])
        collapsed = "".join(pieces)
        return re.sub(r"\s{2,}", " ", collapsed).strip()

    def _trim_overlapping_prefix(self, previous: str, new: str) -> str:
        previous_tokens = self._transcript_tokens(previous)
        new_tokens = self._transcript_tokens(new)

        if not previous_tokens or not new_tokens:
            return new.strip()

        previous_words = [word for word, _, _ in previous_tokens]
        new_words = [word for word, _, _ in new_tokens]
        max_overlap = min(len(previous_words), len(new_words))

        for overlap_size in range(max_overlap, 0, -1):
            if previous_words[-overlap_size:] == new_words[:overlap_size]:
                cut_index = new_tokens[overlap_size - 1][2]
                return new[cut_index:].lstrip()

        # Some ASR windows re-introduce the previous suffix after a short preamble.
        # If a sufficiently long previous suffix appears later in the new chunk,
        # trim through that overlap and only keep genuinely new trailing words.
        min_embedded_overlap_words = 5
        for overlap_size in range(max_overlap, min_embedded_overlap_words - 1, -1):
            previous_suffix = previous_words[-overlap_size:]
            max_start = len(new_words) - overlap_size
            for start_index in range(1, max_start + 1):
                if new_words[start_index:start_index + overlap_size] == previous_suffix:
                    cut_index = new_tokens[start_index + overlap_size - 1][2]
                    return new[cut_index:].lstrip()

        return new.lstrip()

    def _strip_prompt_echo(self, text: str) -> str:
        if not text:
            return ""

        # Guard against occasional prompt leakage from ASR (e.g. "Possible keywords: ...").
        return re.sub(r"\s*possible\s+keywords\s*:\s*.*$", "", text, flags=re.IGNORECASE).strip()

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9%]+", text.lower())]

    def _matches_any(self, tokens: list[str], options: list[str]) -> Optional[str]:
        if not options:
            return None
        for token in tokens:
            if token in options:
                return token
        return None

    def parse_command(self, text: str) -> Optional[dict]:
        if not text:
            return None

        tokens = self._tokenize(text)
        if not tokens:
            return None

        wakeword = None
        for candidate in self.wakewords:
            if candidate in tokens:
                wakeword = candidate
                break

        if wakeword is None:
            return None

        wakeword_index = tokens.index(wakeword)
        tokens_after = tokens[wakeword_index + 1:]

        for command in self.commands:
            verb = self._matches_any(tokens_after, command["verb"])
            obj = self._matches_any(tokens_after, command["object"])
            modifier = self._matches_any(tokens_after, command["modifier"])

            if verb is None or obj is None:
                continue

            if command["modifier"]:
                if modifier is None:
                    modifier = command["modifier"][0]
            else:
                modifier = "on"

            return {
                "wakeword": wakeword,
                "verb": verb,
                "object": obj,
                "modifier": modifier,
                "command": command,
            }

        return None

    def longestCommonSubsentence(self, new: str) -> str:
        """
        Returns the longest common subsentence between the current message and a new message.

        Args:
            new (str): The new message to compare with the current message.

        Returns:
            str: The longest common subsentence.
        """
        # Split both messages into words
        words1 = [word for word, _, _ in self._transcript_tokens(self.message)]
        words2 = [word for word, _, _ in self._transcript_tokens(new)]

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

    def _write_output_chunk(self, text: str) -> None:
        if not text:
            return

        if self.printOut and self.proc and self.proc.stdin:
            if self._has_output_written and not text.startswith((" ", "\t", "\n")):
                self.proc.stdin.write(" ")
            self.proc.stdin.write(text)
            self.proc.stdin.flush()
            self._has_output_written = True

    def searchKeywords(self) -> Optional[dict]:
        """Searches for keywords in the current message and performs actions based on them."""
        command = self.parse_command(self.message)
        if command is None:
            self._command_lock_key = None
            return None

        command_key = command["command"]["raw"]
        if self._command_lock_key == command_key:
            return command

        if self.on_command is not None:
            self.on_command(command)
            self._command_lock_key = command_key

        return command

    def addNewWords(self, new: str) -> None:
        """Takes old string and new string, finds longest common subsentence, and print the new words

        Args:
            new (str): The new message to compare with the current message.

        Returns:
            None
        """

        normalized_new = self._collapse_adjacent_duplicate_words(new)
        normalized_new = self._strip_prompt_echo(normalized_new)
        new_words = self._trim_overlapping_prefix(self.message, normalized_new)
        if new_words:
            self._write_output_chunk(new_words)

        # Update the current message to the new message
        self.message = normalized_new
        self.searchKeywords()


if __name__ == "__main__":
    print(f"{__file__} is not meant to be run as main")