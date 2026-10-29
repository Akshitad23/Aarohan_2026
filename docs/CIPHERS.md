# Cipher catalog for organizers

Each team receives two encrypted words with independent protocols. The server chooses a combination randomly once and stores that assignment with the session. Reconnecting or changing workers preserves it. A public team ID does not predict the combination.

The supplied catalog is suitable for rehearsal. This repository and this document contain its answers. Use a private catalog for the competition and keep this document away from participant laptops. Browser responses contain ciphertext and released hints, never the answer fields.

| ID | First word | First ciphertext | First protocol | Second word | Second ciphertext | Second protocol |
| --- | --- | --- | --- | --- | --- | --- |
| TG-01 | ROVER | YVCLY | Caesar, forward 7 | READY | IVZWB | Atbash |
| TG-02 | LUNAR | OXQDU | Caesar, forward 3 | ORBIT | LIYRG | Atbash |
| TG-03 | SOLAR | FBYNE | ROT13 | FLARE | ERALF | Reversal |
| TG-04 | COMET | XLNVG | Atbash | TRAIL | YWFNQ | Caesar, forward 5 |
| TG-05 | SPACE | ECAPS | Reversal | PROBE | CEBOR | ROT13 |
| TG-06 | EARTH | IEVXL | Caesar, forward 4 | VENUS | IRAHF | ROT13 |
| TG-07 | RADIO | IZWRL | Atbash | WAVES | SEVAW | Reversal |
| TG-08 | NOVA | ABIN | ROT13 | STAR | BCJA | Caesar, forward 9 |
| TG-09 | COSMIC | CSIOMC | Odd-even transposition | SIGNAL | 19-9-7-14-1-12 | A1Z26 |
| TG-10 | GALAXY | 7-1-12-1-24-25 | A1Z26 | NEBULA | NBLEUA | Odd-even transposition |
| TG-11 | LAUNCH | LUCANH | Odd-even transposition | MODULE | SUJARK | Caesar, forward 6 |
| TG-12 | SATURN | 19-1-20-21-18-14 | A1Z26 | METEOR | NVGVLI | Atbash |

Caesar keys above describe encoding. Students reverse the shift to decode. Atbash pairs A/Z, B/Y, continuing inward. ROT13 shifts by 13 positions. Reversal reads the word backward. A1Z26 maps A=1 through Z=26, with hyphens separating numbers. Odd-even transposition encodes the letters in odd positions followed by the letters in even positions, using positions starting at 1.

For odd-even decoding, split after the ceiling of half the text length, then interleave both halves. For example, PLANET becomes PAELNT. Split PAE/LNT and interleave to recover PLANET.

Each word has three eligible prompting techniques. Any one meaningful targeted technique releases the full pack at once: protocol name, concept, operation and key where relevant, and an unrelated worked example. The bot never gives the decoded challenge word. Students can submit a word they have solved independently.

The six techniques are `override`, `roleplay`, `decomposition`, `authority`, `fiction`, and `hypothesis`. The mapping rotates across supplied combinations:

| Combinations | First word techniques | Second word techniques |
| --- | --- | --- |
| TG-01, TG-07 | override, roleplay, decomposition | authority, fiction, hypothesis |
| TG-02, TG-08 | roleplay, decomposition, authority | fiction, hypothesis, override |
| TG-03, TG-09 | decomposition, authority, fiction | hypothesis, override, roleplay |
| TG-04, TG-10 | authority, fiction, hypothesis | override, roleplay, decomposition |
| TG-05, TG-11 | fiction, hypothesis, override | roleplay, decomposition, authority |
| TG-06, TG-12 | hypothesis, override, roleplay | decomposition, authority, fiction |

One accepted model response is required before the planned hint is committed. If both providers are unavailable, the request returns a retryable error and no clue is released.

## Private competition catalog

Save a JSON file outside `frontend/` and the Git repository. Set `CIPHER_CATALOG_PATH` to its absolute path on the deployment server, or store the JSON in the masked `CIPHER_CATALOG_JSON` environment variable. Set only one catalog source. Each entry needs exactly two words. The server computes the ciphertext, so the organizer does not have to type or maintain it.

```json
[
  {
    "id": "private-01",
    "words": [
      {"answer": "ORBITAL", "protocol": "caesar", "key": 4},
      {"answer": "CAPSULE", "protocol": "atbash"}
    ]
  }
]
```

Answers must contain 3 to 16 uppercase ASCII letters. Protocol IDs are `caesar`, `atbash`, `rot13`, `reverse`, `a1z26`, and `odd_even`. Caesar keys must be 1 through 25. Other protocols ignore the optional key. The server rejects an answer that already appears in either word's ciphertext or protocol teaching text. Worked examples avoid both challenge answers. Session persistence stores the chosen puzzle, so changing the catalog does not alter teams already playing.

Private entries receive the same rotating technique groups automatically. To set them explicitly, add a `techniques` array with exactly three supported technique IDs to each word. Both groups must be disjoint and cover all six techniques. The selected mapping persists with the session.

The protocols differ in difficulty. Reversal and A1Z26 can be recognized by appearance; odd-even transposition requires more positional reasoning. For ranked play, give all teams a private catalog with the same protocol pair and comparable word lengths. Different protocol pairs are useful for practice or separate difficulty groups. A large mixed catalog alone does not establish equal difficulty.
