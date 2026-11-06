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
      "action": "appointed | elected | resigned | retired | terminated | not_standing_for_reelection",
      "event_date": "YYYY-MM-DD or null",
      "effective_date": "YYYY-MM-DD or null"
    }
  ]
}
```

## Category

- **leadership_change**: the filing announces at least one qualifying event (see below) for a named person.
- **compensation**: the filing is only about pay, awards, plans or agreements, with no qualifying leadership event. `events` is `[]`.
- **other**: anything else (for example a plan approval or a filing with no usable content). `events` is `[]`.
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
- **action**: `resigned` = person decided to leave (includes "step down"). `retired` = the filing says retire. `terminated` = the company ended the employment or removed the person. `appointed` = officer role. `elected` = board seat. `not_standing_for_reelection` = director will not stand for another term.
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