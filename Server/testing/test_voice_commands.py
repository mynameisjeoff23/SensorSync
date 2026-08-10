import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from Server.voice.Speech import Speech


class SpeechCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        command_file = Path(__file__).resolve().parents[1] / "Server" / "voice" / "commands.txt"
        self.speech = Speech(printOut=False, command_file=command_file)

    def test_add_new_words_inserts_space_between_successive_chunks(self) -> None:
        class DummyProc:
            def __init__(self) -> None:
                self.writes = []

            @property
            def stdin(self):
                return self

            def write(self, data: str) -> None:
                self.writes.append(data)

            def flush(self) -> None:
                return None

        proc = DummyProc()
        self.speech.printOut = True
        self.speech.proc = proc

        self.speech.addNewWords("hello")
        self.speech.addNewWords("hello world")

        self.assertEqual("".join(proc.writes), "hello world")
        self.assertTrue(proc.writes[1].startswith(" "))

    def test_parse_command_with_wakeword_and_synonyms(self) -> None:
        parsed = self.speech.parse_command("jarvis turn off the lights")

        self.assertEqual(parsed["wakeword"], "jarvis")
        self.assertEqual(parsed["verb"], "turn")
        self.assertEqual(parsed["object"], "lights")
        self.assertEqual(parsed["modifier"], "off")

    def test_parse_command_requires_wakeword(self) -> None:
        parsed = self.speech.parse_command("turn off the lights")

        self.assertIsNone(parsed)

    def test_parse_command_accepts_labeled_slots_in_any_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command_file = Path(temp_dir) / "commands.txt"
            command_file.write_text(
                "wakewords: computa\n\ncommands:\nmodifier: off object: lights verb: turn/power\n",
                encoding="utf-8",
            )

            speech = Speech(printOut=False, command_file=command_file)
            parsed = speech.parse_command("computa turn the lights off")

        self.assertEqual(parsed["wakeword"], "computa")
        self.assertEqual(parsed["verb"], "turn")
        self.assertEqual(parsed["object"], "lights")
        self.assertEqual(parsed["modifier"], "off")

    def test_search_keywords_executes_registered_handler(self) -> None:
        events = []
        self.speech.on_command = lambda command: events.append(command)

        self.speech.addNewWords("computa turn off the lights")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["wakeword"], "computa")
        self.assertEqual(events[0]["modifier"], "off")

    def test_search_keywords_locks_overlapping_transcriptions(self) -> None:
        events = []
        self.speech.on_command = lambda command: events.append(command)

        self.speech.addNewWords("computa turn off the lights now")
        self.speech.addNewWords("turn off the lights now please")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["verb"], "turn")

    def test_add_new_words_collapses_repeated_overlap_words(self) -> None:
        class DummyProc:
            def __init__(self) -> None:
                self.writes = []

            @property
            def stdin(self):
                return self

            def write(self, data: str) -> None:
                self.writes.append(data)

            def flush(self) -> None:
                return None

        proc = DummyProc()
        self.speech.printOut = True
        self.speech.proc = proc
        self.speech.message = "Besides, if there is hostile intent."

        self.speech.addNewWords(
            "intent what would I do about it? Die, that's what I would do. I'm a scientist. scientist, not bug Raju's"
        )

        self.assertEqual(
            "".join(proc.writes),
            "what would I do about it? Die, that's what I would do. I'm a scientist. not bug Raju's",
        )

    def test_parse_command_uses_default_modifier_when_missing(self) -> None:
        parsed = self.speech.parse_command("jarvis turn the lights")

        self.assertEqual(parsed["wakeword"], "jarvis")
        self.assertEqual(parsed["verb"], "turn")
        self.assertEqual(parsed["object"], "lights")
        self.assertEqual(parsed["modifier"], "off")

    def test_add_new_words_trims_embedded_overlap_from_window_drift(self) -> None:
        class DummyProc:
            def __init__(self) -> None:
                self.writes = []

            @property
            def stdin(self):
                return self

            def write(self, data: str) -> None:
                self.writes.append(data)

            def flush(self) -> None:
                return None

        proc = DummyProc()
        self.speech.printOut = True
        self.speech.proc = proc
        self.speech.message = "I don't know anything about the virus"

        self.speech.addNewWords(
            "What else don't you know? I don't know anything about the virus so you do know about the pirates."
        )

        self.assertEqual(
            "".join(proc.writes),
            "so you do know about the pirates.",
        )

    def test_add_new_words_strips_prompt_keyword_echo(self) -> None:
        class DummyProc:
            def __init__(self) -> None:
                self.writes = []

            @property
            def stdin(self):
                return self

            def write(self, data: str) -> None:
                self.writes.append(data)

            def flush(self) -> None:
                return None

        proc = DummyProc()
        self.speech.printOut = True
        self.speech.proc = proc
        self.speech.message = "take care of yourself"

        self.speech.addNewWords("take care of yourself. Possible keywords: times, to")

        self.assertEqual("".join(proc.writes), "")
