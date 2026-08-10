These are the classes and files that pertain to the voice processing part of the sever.

##Creating a voice command

Apart from the wakewords, every command needs a verb, an object, and a modifier. For example in the sentence: "clanker turn off the lights" — `turn` is the verb, `lights` is the object, and `off` is the modifier.

Commands can be written in any slot order when you label them. For example, `modifier: off object: lights verb: turn/power` is equivalent to `verb: turn/power object: lights modifier: off`.

Structure rules:
- Verb: the action to perform (e.g. `turn`, `set`, `play`).
- Object: the target of the action (e.g. `light`, `volume`, `fan`).
    - Prefer singular nouns: use singular forms for best intent recognition (e.g. `light` rather than `lights`). Plural forms are accepted, but singulars typically yield more accurate parsing.
- Modifier: additional detail for the verb/object (e.g. `on`, `off`, `50%`, `green`).

Equivalence with slashes:
You can combine words that should be treated as equivalent by separating them with a slash. For example `power/turn` means the parser will accept either `power` or `turn` in the verb position, so "computa power off the lights" is equivalent to "computa turn off the lights".

Default modifiers:
If a modifier is omitted, a sensible default will be assumed (configured per command). In other words, if the user says only the wakeword, verb, and object, the system applies the command's default modifier so the intent is still satisfied without requiring every word.