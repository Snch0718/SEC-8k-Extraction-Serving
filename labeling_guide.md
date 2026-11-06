# Labeling guide: 8-K Item 5.02 extraction (v1)

**Task.** Given the text of the Item 5.02 section of an 8-K, produce one JSON object describing leadership changes announced in that filing.

## Output format

```json
{
  "category": "leadership_change | compensation | other",
  "events": [
    {
      "who": "full name of the person",
      "role": "title or board seat as written",
      "action": "appointed | elected | resigned | retired | terminated | not_standing_for_reelection | departed",
      "event_date": "YYYY-MM-DD or null",
      "effective_date": "YYYY-MM-DD or null"
    }
  ]
}
```

## Category

- **leadership_change**: the filing announces at least one qualifying event (see below) for a named person.
- **compensation**: the filing is only about pay, awards, plans or agreements, with no qualifying leadership event. `events` is `[]`.
- **other**: anything that is neither a leadership change nor about pay, plans or agreements (for example a filing with no usable content).
- If a filing has both a leadership event and pay terms, the category is `leadership_change`. Label the leadership events only and ignore the pay terms. (Compensation extraction is out of scope for v1.)

## What counts as an event

1. **Include** a change only if this filing is the one announcing it, or reporting a decision with a stated outcome. Test: would a reader learn this news from this filing?
2. **Exclude** background: "as previously reported", passing mentions of a possible or future step ("may retire", "in anticipation of his upcoming retirement" given only as the reason for a pay decision), and descriptions of agreements in force.
3. One event per person per action. A promotion or role change counts as `appointed` to the new role. Do not also create a departure event for the old role.
4. If one person is appointed to several roles in the same sentence, use one event and join the roles with " and ".
5. Groups ("named executive officers") are not allowed in `who`. If the only subject is a group, the filing has no events.
6. If a filing has more than 8 events, set it aside as "too long" and keep it out of the test set.

## Field rules

- **who**: name as written, without titles such as Mr., Ms., Dr.
- **role**: as written, trimmed. For board seats use "Director" (ignore committee memberships).
- **action**: `resigned` = person decided to leave (includes "step down"). `retired` = the filing says retire. `terminated` = the company ended the employment or removed the person. `appointed` = officer role. `elected` = board seat. `not_standing_for_reelection` = director will not stand for another term. `departed` = the filing says the person is leaving or has left, but doesn't say whether by resignation, retirement or termination.
- **event_date**: the date the decision, notice or approval happened, if the filing gives one.
- **effective_date**: the date the change takes effect. Use `null` if it is conditional or not stated. Partial dates (month and year only) become `null`.
- When unsure, use `null` instead of guessing, and add a note in the labeling sheet (not in the JSON).

## Worked examples

**Analog Devices (Nov 2024)**: Gregory Bryant gave notice of his resignation as Executive Vice President and President of Business Units, effective upon the appointment of his replacement. Staying through March 31, 2025 is not captured in v1.

```json
{"category": "leadership_change", "events": [{"who": "Gregory Bryant", "role": "Executive Vice President and President of Business Units", "action": "resigned", "event_date": "2024-11-17", "effective_date": null}]}
```

**Abbott (Nov 2024)**: change-in-control agreements extended for named executive officers. No individual, no leadership event.

```json
{"category": "compensation", "events": []}
```

**Chevron (Jan 2025)**: salary, bonus and equity decisions. One executive's retirement is mentioned only as the reason for no pay change, so it is background.

```json
{"category": "compensation", "events": []}
```

## Process

1. Label the test set yourself, before looking at any model output.
2. Re-label 20 of those filings two days later without looking at your first answers. Report how often the two passes agree. That agreement is a ceiling on any model's score.
3. Record every rule you had to invent as a new line in this guide, with the date.

## Rule log

Rules added while labeling. Format: date, rule.

- 2026-11-06: Write "&" in titles as "and" (for example "Co-President and Chief Investment Officer"), so one title never has two spellings.
- 2026-11-06: Ignore line breaks in the text. A title split across lines is written as one line.
- 2026-11-06: Biography sentences (age, education, past roles, earlier appointments) are background. Never label them, and give no event to people mentioned only in passing.
- 2026-11-06: Succession: if a filing says person A hands a role to person B, label B as `appointed`. Label A only if the filing also says A leaves the company (`resigned`, `retired` or `terminated`). Moving to other duties is not a departure.
- 2026-11-06: A future departure counts as an event if the filing states it as definite and is the one announcing it, even without a date (`effective_date` is null). It does not count if it is only mentioned as the reason for something else, or if it is hedged ("may", "expects to consider").
- 2026-11-06: When a person keeps other duties, use the title of the role being changed, as written in the filing.
- 2026-11-06: event_date is only filled when the filing gives a date for that person’s own decision, notice or announcement. Do not copy another person’s date onto a successor’s event. Use null instead.
- 2026-11-06: Drop nicknames in quotation marks from names (write "Andrew Macdonald", not Andrew "Mac" Macdonald).
- 2026-11-06: New action `departed` for a departure where the filing does not say resigned, retired or terminated. Never guess a reason.
- 2026-11-06: "Effective immediately" sets an event's effective_date only when the sentence clearly attaches it to that event. If it could cover several events, use null for the unclear ones.
- 2026-11-06: An interim role ending is not an event when the person stays at the company.
- 2026-11-06: The action follows the role type, not the filing's verb. A board seat is `elected` even if the filing says "appointed". An officer role is `appointed`.
- 2026-11-06: If a filing gives only one date for a past-tense action and no separate effective date, fill event_date and leave effective_date null.
- 2026-11-06: Equity or incentive plan approvals and amendments are `compensation`, not `other`. `other` is for filings that are neither leadership nor compensation.
- 2026-11-06: When a person steps down from a role but stays at the company until a later retirement, label the retirement with the retirement date as effective_date and use the title of the role they are leaving.
- 2026-11-06: Write names as they appear in the filing, keeping middle initials (for example "Daniel S. Tucker"), but without titles such as Mr. or Ms.
- 2026-11-06: An effective date may be well after the filing date. Record it as stated. Do not leave it null just because it is in the future.
- 2026-11-06: In titles, write any dash (hyphen, en dash, em dash) as a plain hyphen "-", so one title never has several spellings.
- 2026-11-06: "Effective immediately" attached to a resignation, retirement or appointment sets effective_date to the same date as event_date. Without that wording or another stated date, effective_date stays null.
- 2026-11-06: A person who moves to a new, named role is `appointed` to that role, even if they stay at the company. A person who only hands off a role, with no new title in the filing, gets no event. Use the date the filing states for the move, even if it is the last day in the old role.
- 2026-11-06: Keep name suffixes (Jr., Sr., II, III) as part of the name. Drop nicknames in quotation marks and titles such as Mr., Ms., Dr.
- 2026-11-06: A phrase like "intends to pursue other opportunities" without the word resign, retire or terminated is `departed`.
- 2026-11-06: An effective date attached to pay changes (for example "compensation changes effective April 21") is not the effective date of the appointment. Use only the date tied to the role change itself.
- 2026-11-06: Record dates exactly as the filing states them, even if they look inconsistent (for example an effective date before the approval date). Flag the oddity in the notes field, and do not correct it.
- 2026-11-06: If one person's roles need different actions (an officer role is `appointed`, a new board seat is `elected`), create one event per action, not one joined event. Rule 4 (join roles with "and") applies only when the action is the same.
- 2026-11-06: A new title for someone already on the board (Chair, Executive Chair, Lead Independent Director) is `appointed` to that title. `elected` is only for gaining a board seat.
- 2026-11-06: If the filing defines a term for a date (for example "Transition Date"), resolve it to the actual date.
- 2026-11-06: If the filing gives only part of a name (for example "D. Adamczyk"), write it exactly as given. Never add details from outside the filing.
- 2026-11-06: A date tied to something else mentioned in the filing (for example the announcement of a new job elsewhere) is not the event_date.
- 2026-11-06: "As previously announced/reported" excludes an item only when it is background to a different event. If the filing's main subject is that item taking effect (for example a director's retirement taking effect), it is an event. Test: if you removed this item, would the filing have no news left?
- 2026-11-06: Added responsibilities without a new title (for example "assumed responsibility for...") are not an event. Only a new named title or board seat counts.
- 2026-11-06: Drop nicknames whether they are in quotation marks or in parentheses.
- 2026-11-06: "On or about [date]" counts as that date. Enter it and mention the hedge in the notes. Partial dates (month and year only) are still null.