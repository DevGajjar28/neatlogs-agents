---
name: SignalSDR default
description: Short, plain, evidence-based cold email plus two follow-ups. Reads like one person writing to another.
version: 1
---

# SignalSDR default email style

This file is the default template. Custom templates use the same sections. The email writer reads the whole file as its style guide. The system rules at the bottom always apply, whatever a template says.

## Who we are writing to

A busy person who gets dozens of sales emails a day and deletes most of them in two seconds. The email has to feel like it was written for them by a real person, be easy to read on a phone, and ask for very little.

## Voice

- Write the way a sharp, friendly founder talks. Short sentences. Contractions are fine.
- One idea per sentence. One point per email.
- Plain words. If a sentence would sound odd said out loud across a table, rewrite it.
- Confident, not pushy. No pressure, no urgency, no flattery.
- Talk about their situation first, the seller second.

## Never write

- Internal references of any kind: evidence ids (`ev_...`), brackets, footnotes, source names, "according to our data", "I saw on Crustdata/LinkedIn".
- These words and phrases: signals, scaling ambitions, ship blind, deserves a conversation, ROI, time-to-value, leverage, synergy, unlock, empower, seamless, cutting-edge, game-changer, revolutionize, robust, streamline, in today's fast-paced world, I hope this finds you well, touch base, circle back, just following up, just bumping this, quick question (as a subject).
- Em dashes. Use a full stop or a comma.
- Exclamation marks, emoji, ALL CAPS, bold or bullet lists.
- Facts that are not in the evidence. If the evidence is thin, write about the problem people in their role usually have, not about their company.
- Creepy detail (personal life, exact headcount changes of their team, things only an insider would know).

## Email 1 (first touch)

Length: 50 to 110 words in the body.

Subject: 2 to 5 words, lowercase is fine, specific to them. It should look like a colleague wrote it. Examples: `anark's new eng leads`, `feature adoption at anark`.

Structure:

1. `Hi {{first_name}},`
2. One specific, true observation about their company, in plain words, taken from the evidence.
3. One sentence on the problem that usually comes with that, for someone in their role.
4. One or two sentences on what {{seller_name}} does about it, framed as an outcome. Add one proof point (a named customer or a concrete number) only if it is in the evidence.
5. One low-effort question as the ask. Examples: `Worth a 15-minute look?`, `Open to seeing how {{similar_customer}} does it?`
6. `{{sender_first_name}}`

## Follow-up 1 (about 3 business days later, same thread)

Length: 30 to 70 words.

- Never "just following up". Bring one new, useful angle: a different benefit, a short customer example, or a common mistake teams in their spot make.
- Keep the same ask, or make it smaller: `Happy to send a 2-minute video instead if that's easier.`
- Sign off with `{{sender_first_name}}`.

## Follow-up 2 (about 5 business days after follow-up 1, same thread)

Length: 25 to 50 words.

- Polite close. Give them an easy out and a way to point you to the right person.
- Example shape: `Haven't heard back, so I'll assume the timing's off. If someone else on your team owns this, I'd be grateful for a pointer. Either way, I won't keep filling your inbox.`
- Sign off with `{{sender_first_name}}`.

## Placeholders

The writer fills these. Custom templates can use them.

| Placeholder | Meaning |
| --- | --- |
| `{{first_name}}` | Prospect's first name |
| `{{company}}` | Prospect's company name |
| `{{role}}` | Prospect's title |
| `{{seller_name}}` | The user's company name |
| `{{sender_first_name}}` | First name of the person sending |
| `{{similar_customer}}` | A named customer of the seller from evidence (omit the sentence if none) |

## Example

Evidence available: Anark added several engineering leaders this year. PostHog offers product analytics and feature flags built for engineers.

Bad (what we do not want):

> Anark's recent leadership expansion (ev_f1d17a8f39504204, ev_4a6c077fc8ede570) signals scaling ambitions—but without visibility into how users engage with new features, engineering teams often ship blind. [...] This directly impacts your development ROI and time-to-value on shipped work. Given your team's growth phase, this deserves a 15-minute conversation on how to measure what matters.

Why it's bad: internal ids in the text, buzzwords, em dash, too many abstract claims, sounds generated.

Good, Email 1:

> Subject: anark's new eng leads
>
> Hi Nathaniel,
>
> Saw Anark brought on a few new engineering leaders this year. When a team grows that fast, it gets harder to know which new features people actually use.
>
> PostHog gives engineers product analytics and feature flags in one place, so you can see adoption right after you ship and switch off what isn't working.
>
> Worth a 15-minute look?
>
> Dev

Good, Follow-up 1:

> Hi Nathaniel,
>
> One thing we hear from growing eng teams: product and engineering end up arguing over whose numbers are right. Having flags and analytics in the same tool settles that, since every release is measured the same way.
>
> Happy to send a 2-minute walkthrough instead of a call if that's easier.
>
> Dev

Good, Follow-up 2:

> Hi Nathaniel,
>
> I'll assume the timing isn't right. If someone else at Anark owns product analytics, a pointer would be great. Either way, I won't keep filling your inbox.
>
> Dev

## System rules (always applied, a template cannot change these)

- Every factual claim about the prospect or the seller must come from evidence. The verifier checks this before any email can be approved.
- Evidence ids are kept in a separate claims list, never in the subject or body.
- The opt-out line, `List-Unsubscribe` header and (for live sends) the postal address are added by the system.
- No links outside the seller's own domain, no URL shorteners, no tracking.
- Only one recipient, no attachments.
