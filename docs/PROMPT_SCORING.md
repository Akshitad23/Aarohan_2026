# Post-event prompt grading

A team can earn 10 marks in each event session. Morning and Afternoon keep separate registrations, clocks, logs and results.

| Component | Maximum | Award rule |
| --- | ---: | --- |
| Timeline | 2 | All five cards in chronological order within three attempts and ten minutes |
| First word | 2 | Correct answer submitted for that word |
| Second word | 2 | Correct answer submitted for that word |
| Prompt quality | 4 | Organizers grade the recorded transcript after the event session ends |

The live dashboard shows objective marks out of 6. Prompt quality stays pending, and the final score out of 10 stays empty, until an organizer saves a grade. The application does not award automatic quality marks. Speed, prompt count and clue discovery do not add or subtract marks.

## Quality rubric

Grade the strongest coherent prompt or sequence in the team's transcript. Use 0, 0.5 or 1 for each criterion. Equivalent wording and reasonable paraphrases count.

| Criterion | 0 | 0.5 | 1 |
| --- | --- | --- | --- |
| Clear task | No usable request | Recognizable but ambiguous intent | Clearly requests an explanation, protocol hint, comparison or check |
| Relevant context | No connection to the puzzle | Identifies a word or repeats a clue | Uses a relevant observation or previously released information about the target word |
| Useful constraint or format | No useful direction | Vague direction | Sets a useful limit or format, such as a hint without the answer or an unrelated worked example |
| Testing or refinement | No test or improvement | Requests an example without examining it | Tests a hypothesis, checks an example, or improves an earlier prompt using the reply |

Length, grammar, technical vocabulary and successful jailbreaks do not earn quality marks by themselves. A failed unlock can still contain a good prompt. Read failed provider requests too, since an API outage should not make a student's writing invisible to judges. A failed provider request does not count as an accepted turn or unlock a hint.

Before the event, have two organizers grade the same practice transcripts and settle disagreements. During grading, cite turn numbers or short evidence in the reason field. Ask a second judge to review close rankings and ties. The application stores each saved review in an audit history.

## Export one event session

Select Morning or Afternoon in the admin dashboard, then download its Excel workbook. The export includes:

| Worksheet | Contents |
| --- | --- |
| Summary | Objective marks, pending or reviewed quality, final score and team status |
| Event | Session times, scoring rules, rubric and import instructions |
| Teams | Registration IDs, names, schools, sizes and registration times |
| Participants | Every registered participant and grade |
| Prompts | Every accepted prompt and response, every failed AI request, target, technique, provider, timestamps, latency and complete telemetry |
| TimelineAttempts | Each recorded timeline submission, placement, slot result and outcome |
| WordAnswers | Correct, incorrect and closed-session answer submissions |
| QualityReview | Editable judging template with stable batch and team IDs |
| ReviewAudit | Earlier saved grades, reasons and timestamps |

Access tokens and token hashes are excluded. Text is stored as literal text to prevent spreadsheet formulas from running. Values longer than 30,000 characters continue in numbered columns. XML control characters appear as Unicode escapes. Earlier versions did not record individual timeline submissions or guesses, so those older attempts cannot be reconstructed from totals.

## Grade in the workbook

Keep `batch_id` and `team_id` unchanged. In `QualityReview`, fill either:

- `score` from 0 to 4 and `reason`; or
- all four criterion columns from 0 to 1 and `reason`, leaving `score` blank.

The criterion columns are `clear_task_0_to_1`, `relevant_context_0_to_1`, `constraint_0_to_1` and `testing_refinement_0_to_1`. Their sum becomes the quality score when `score` is blank. If `score` is filled, it is the grade to import. Use numeric values, not formulas. Completely ungraded rows are skipped, allowing a judge to finish a subset of teams.

A CSV can use this simpler schema:

```csv
batch_id,team_id,score,reason
morning,AAR-EXAMPLE,3.5,"Turns 2 and 4 identify the target and test a mapping; the output limit is incomplete."
```

The example ID is a placeholder. Use the IDs from the export.

## Validate and import

Run these commands from the repository folder. Configure `DATABASE_URL` for the event database in `backend/.env` or the process environment. Local work can use the configured SQLite database instead. Do not point a practice grading file at the live event database.

```powershell
python backend/grade_reviews.py C:\Event\morning-grades.xlsx
python backend/grade_reviews.py C:\Event\morning-grades.xlsx --apply
```

The first command validates without changing any grades. The second validates every completed row, then applies the whole file in one transaction. CSV files use the same commands. A wrong batch/team combination, duplicate team, missing reason, invalid score or event session that has not ended rejects the file before any grade is written.

Applying a revised grade replaces the current quality component and appends a new audit entry. It preserves timeline and word marks. Final score equals objective marks plus reviewed quality, with a maximum of 10. Download a new workbook after importing to capture the reviewed results.

Organizers can also grade one team through Review in the admin dashboard after its event session ends. The same score bounds and required reason apply.

## Keep grading separate from the game model

The chatbot is the system students are trying to influence. Its conversation does not decide their quality marks. A future offline AI judge could propose evidence against this fixed rubric, but organizers should review those suggestions before importing them. This version provides the complete transcript, editable template, validation and audit trail for that workflow.
