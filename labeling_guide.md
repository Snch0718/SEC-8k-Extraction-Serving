# Labeling guide: 8-K Item 5.02 extraction (v1.1)

Merged 2026-11-12 from v1 and its rule log (the log is in git history). Where two log entries disagreed, this version says which one wins.

**Task.** Given the text of the Item 5.02 section of an 8-K, produce one JSON object describing the leadership changes the filing announces.

## 1. Output format

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

## 2. Category

- **leadership_change**: the filing announces at least one qualifying event (section 3) for a named person.
- **compensation**: the filing is only about pay, awards, equity or incentive plans (including plan approvals and amendments), bonus criteria or pay agreements, with no qualifying event. `events` is `[]`.
- **other**: anything that is neither of the above, for example a temporary leave with no new title, or a filing with no usable content. `events` is `[]`.
- If a filing has both a leadership event and pay terms, the category is `leadership_change`. Label the leadership events only. Pay terms are out of scope in v1.

## 3. What counts as an event

**Include**

1. A change that this filing announces, or a decision with a stated outcome. A future departure or appointment counts if the filing states it as definite, even without a date. Test: would a reader learn this news from this filing? If you removed the item, would the filing have no news left?
2. A person moving to a new named title (promotion, move, interim title) is `appointed` to it. A new board seat is `elected`. A new title for someone already on the board (Chair, Executive Chair, Lead Independent Director) is `appointed`.
3. A person who the filing says resigns, steps down, retires, is terminated, or is departing from a named role or board seat.

**Exclude**

- Background: biography, earlier appointments, "previously announced" items that only give context for a different event, a retirement mentioned only as the reason for a pay decision, and hedged steps ("may", "expects to consider").
- Added responsibilities with no new title ("assumed responsibility for...").
- A role handed to someone else, when the person gets no new title and the filing states no departure.
- An interim role ending while the person stays at the company.
- Committee memberships, committee chair changes, board size changes.
- Board nominations awaiting a shareholder vote, and appointments to a subsidiary's or another entity's board.
- Groups ("named executive officers"): `who` is always a named person.
- Pay terms of any kind.

If a filing has more than 8 events, set it aside as too long and keep it out of the test set.

## 4. Actions

- `appointed`: officer role or new title (including interim).
- `elected`: board seat. The action follows the role type, not the filing's verb: a director "appointed" by the board is `elected`.
- `resigned`: the person decided to leave (includes "step down").
- `retired`: the filing says retire.
- `terminated`: the company ended the employment or removed the person.
- `not_standing_for_reelection`: a director will not stand for another term.
- `departed`: the filing says the person is leaving or has left, but not how ("pursue other opportunities" counts). Never guess a reason.

## 5. Dates

Format `YYYY-MM-DD`. Use `null` when the filing gives no date for that field.

**event_date**: the date the filing attaches to this person's own decision, notice, board action or announcement.
- Never copy it from another person's event, from `effective_date`, from the filing or report date, or from a date tied to something else (a press release, a new job elsewhere).
- If the filing gives only one date for a past-tense action and no separate effective date, that date is the `event_date` and `effective_date` is `null`.
- If the only date is an effective date ("appointed, effective July 25"), `event_date` is `null`.

**effective_date**: the date the change takes effect, as stated.
- "Effective immediately" sets `effective_date` to the date of the action. A trailing "effective immediately" applies to every event in the same sentence.
- For a departure or retirement, use the date the filing attaches to that action ("retire ... effective May 19"). If it attaches none, use the date the person leaves the company, if it is a full date.
- A date attached to pay changes is not the effective date of an appointment.
- A condition ("upon the appointment of his replacement") gives `null`.
- Future dates are recorded as stated.

**Other rules**
- Partial dates (month and year, a quarter, "late 2026") are `null`.
- "On or about [date]" counts as that date. Note the hedge.
- Resolve defined terms ("Transition Date") to the actual date.
- Record dates exactly as stated, even if they look inconsistent (an effective date before the approval date). Do not correct them; note the oddity.

## 6. People with several roles or stages

- Same action and same dates for several roles: one event, with the roles joined by " and ".
- Different actions (an officer role `appointed` and a board seat `elected`) or different dates: one event per role.
- Stepping down from a role and retiring later is one event, with dates per section 5.
- If the filing says a person steps down, resigns or retires from a named role, label it even if the person stays on as an advisor. If it only says they move to other duties or an advisory role, with no step-down or retirement stated, label no departure. Advisory service alone is not a new named leadership role.
- A person who retires as an employee but continues as a director gets no separate event.
- Several appointments effective on the same future date: label each person's new named role. Add departure events for their previous roles only if the filing says they are leaving those roles or the company.

## 7. Names and roles

**who**
- As written in the filing, keeping middle initials and suffixes (Jr., III).
- Drop honorifics, ranks and titles (Mr., Ms., Dr., Admiral), trailing descriptions ("U.S. Navy, Retired"), post-nominal letters (CBE), a leading "the", and nicknames in quotation marks or parentheses.
- A peer keeps the title as the name ("Lord Hill of Oareford").
- If the filing gives only part of a name ("D. Adamczyk"), write it as given. Never add details from outside the filing.

**role**
- As written, trimmed, on one line. Write "&" as "and" and any dash as a plain hyphen "-".
- Leave out committee memberships added to a title ("and member of the Executive Committee").
- Board seats are "Director".
- If the person keeps other duties, use the title of the role being changed.

## 8. Worked examples

These come from companies outside the test set, so they can also be used as few-shot examples.

**Analog Devices (Nov 2024).** Gregory Bryant gave notice of his resignation as Executive Vice President and President of Business Units, effective upon the appointment of his replacement. Staying through March 31, 2025 is not captured.

```json
{"category": "leadership_change", "events": [{"who": "Gregory Bryant", "role": "Executive Vice President and President of Business Units", "action": "resigned", "event_date": "2024-11-17", "effective_date": null}]}
```

**Abbott (Nov 2024).** Change-in-control agreements extended for named executive officers. No individual, no leadership event.

```json
{"category": "compensation", "events": []}
```

**Chevron (Jan 2025).** Salary, bonus and equity decisions. One executive's retirement is mentioned only as the reason for no pay change, so it is background.

```json
{"category": "compensation", "events": []}
```

## 9. Process

1. Label the test set before looking at any model output.
2. Re-label 20 filings later without looking at the first answers, and report the agreement. It is a ceiling on any model's score.
3. Record every new rule with its date in the changelog below.
4. Once the labels are frozen, a rule change means a new dated version of the guide and the labels. Do not edit the frozen file.

## 10. Changelog

- 2026-11-06: v1 written, rule log started during first-pass labeling.
- 2026-11-09: rules added for stages, advisory roles and name cleanup.
- 2026-11-12: second pass done on 20 filings. Rules clarified for `event_date`, trailing "effective immediately", interim titles, peers' names and plan approvals. Rule log merged into this version (v1.1). `event_date` is reported separately in scoring, because it was the field with the lowest agreement.