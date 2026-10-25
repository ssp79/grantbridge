"""How It Works — the six steps of the GrantBridge workflow, written for a nonprofit professional.

A public page: it reads no account's data. The step order is the same one the signed-in walkthrough uses
(`components.WALKTHROUGH`), so the guide and the product cannot drift apart. One registration call to action, at
the end of the journey rather than between every step.
"""

from pathlib import Path

import streamlit as st

from grantbridge import components as c
from grantbridge import public, session

user = session.current_user()
SHOTS = Path(__file__).resolve().parent.parent / "assets" / "previews"

# key: (title, what you do, how GrantBridge helps, expander heading, the guide, screenshot, caption)
STEPS = {
    "profile": (
        "Start with your organization",
        "Describe your mission, your programs, the people you serve and the funding you are looking for.",
        "Everything that follows — matching, eligibility checks, recommendations and drafts — is grounded in these "
        "details, so the time you spend here is repaid on every grant you look at.",
        "How to build your nonprofit profile",
        """**How to do it**

1. Open **Set up** and work through three short screens. Each one saves as you finish it, so you can stop and
   return whenever you like.
2. **Your organization:** enter your organization's name, the state you operate in, and your 501(c)(3) status.
   These are the first things most funders screen on.
3. **What you do:** write your mission in a sentence or two, describe the populations you serve and your main
   programs, and choose your focus areas from the list.
4. **What you are looking for:** enter the size of grant you typically request and, optionally, your annual
   budget and the results you can evidence.
5. Press **Finish setup**. You can refine any field later under **Organization Profile**, and your changes apply
   to every future check immediately.

**Why it matters**

Eligibility screening, mission-fit scoring and drafted answers all draw on this profile. A thin profile produces
vague recommendations and drafts full of blanks; a considered one lets GrantBridge rule opportunities in or out
with confidence, and saves your team from re-explaining the organization on every application.

**Tips for success**

- Write the mission as you would say it to a funder, not as it appears in your bylaws — matching works on
  meaning, and plain language matches better.
- Put concrete figures in **Track record and outcomes** (people served, outcomes measured, grants delivered).
  These are the facts drafts are allowed to quote later.
- Leave a field blank rather than guessing. An empty field is reported as unknown and flagged for you to confirm;
  an inaccurate one quietly skews every assessment.

**What's next**

With a profile in place, grant discovery stops being a keyword search and starts being a comparison against your
organization.""",
        None, None),
    "discover": (
        "Find opportunities worth a look",
        "Search for funding by keyword or programme area, review what each opportunity requires, and save the ones "
        "that look promising.",
        "Each result is compared against your profile as it appears, so you can see at a glance which requirements "
        "you already meet and which need checking.",
        "How to search and save grants",
        """**How to do it**

1. Open **Find Grants** and choose where to search: practice listings while you learn the tool, or live federal
   opportunities.
2. Enter a keyword if you have one — a programme area such as *literacy* or *workforce* works well — or leave it
   blank to see everything matching your profile.
3. Open **Filters** to narrow by focus area, award size, state or deadline status.
4. Read each result's funder, award range, deadline and eligibility summary. GrantBridge marks which checks it
   could run for you and which requirements you must confirm against the funder's own documents.
5. Press **Save** on anything worth a closer look. Saved grants appear under **Saved Grants** and feed your
   pipeline, your portfolio and the dashboard.

**Why it matters**

Most wasted grant effort is spent on opportunities that were never a fit. Filtering early — on geography, award
size and eligibility — is the cheapest hour in the whole process, and it protects your team's time for the
applications you can genuinely win.

**Tips for success**

- Check geographic eligibility before anything else. It is the most common disqualifier and the quickest to read.
- Compare the award range with the amount you actually need. A grant far larger than your usual request often
  brings reporting obligations that outweigh the money.
- Note the deadline before you fall in love with the programme. Three weeks is a very different proposition from
  three months.

**What's next**

Saving a grant does not commit you to applying. The next step is deciding whether it is worth the work.""",
        "site-find.webp",
        "Search results, each showing its funder, award range, deadline and the checks already run against your "
        "profile."),
    "evaluate": (
        "Decide before you write",
        "Put one opportunity through a structured go/no-go review, and find out what winning it would actually "
        "cost you.",
        "You get a clear recommendation, the reasoning behind it, and an explicit list of everything still "
        "unverified — so the decision is yours, made on evidence.",
        "How to evaluate a grant before applying",
        """**How to do it**

1. Open **Should We Pursue?** and choose a saved grant from **Grant or application**.
2. Press **Assess this grant**. GrantBridge reviews six dimensions: eligibility, strategic fit, application
   readiness, time and capacity, budget feasibility and proposal quality.
3. Read the recommendation at the top — *Strong candidate*, *Promising, but verify first*, *Proceed with caution*
   or *Do not pursue under current conditions* — together with the rule that decided it.
4. Work through **What we still need to know**. These are requirements no software can confirm for you. Tick the
   ones you have checked against the funder's documents; your confirmations are recorded as yours and dated.
5. Open the **Can we afford to win?** tab and paste the funder's award terms if you have them. Enter your cash
   reserves, the award you would request and any match already committed, then press **Save my numbers**.
6. Review the result and use **What if** to test a scenario — a longer payment delay, a smaller award, part of
   the money paid in advance — without changing anything you have saved.

**Why it matters**

An attractive grant and an affordable grant are not the same thing. A matching requirement, reimbursement paid
ninety days in arrears, or an overhead cap below your real rate can mean that winning ties up more working
capital than your organization has. Finding that out before you apply protects your cash position; finding out
afterwards is how small organizations get into difficulty.

**Tips for success**

- Enter your cash reserves honestly. The analysis is only as useful as the figure you give it.
- Treat unknowns as questions for the funder, not as problems. The list doubles as an agenda for a call with the
  programme officer.
- If the recommendation surprises you, read the deciding rule rather than dismissing it — it is usually pointing
  at a requirement that deserves a second look.

**What's next**

Once you know which individual grants are worth pursuing, the question becomes which of them you can take on at
once.""",
        "site-pursue.webp",
        "A completed assessment: the recommendation, the rule behind it, and each dimension rated separately."),
    "portfolio": (
        "Choose what to pursue first",
        "Compare the opportunities in front of you against the staff hours you genuinely have.",
        "GrantBridge schedules the work backwards from every deadline and tells you which applications fit, which "
        "should wait, and exactly why.",
        "How to prioritize your funding opportunities",
        """**How to do it**

1. Open **Portfolio Strategist**. It considers every grant you have saved.
2. Set **hours a week** to the time your team can realistically give to grant work — the honest number, not the
   hopeful one.
3. Adjust the priority sliders to reflect what matters to your organization: strategic fit, certainty about
   eligibility, the size of the request, the effort involved and mission alignment.
4. Read the **Recommended portfolio**. Each grant is marked recommended, deferred or excluded, with its reason in
   hours and dates rather than a score.
5. Open **Weekly capacity** to see the same plan week by week, and **Mission drift** to check whether any
   opportunity would pull you away from your stated purpose.
6. Mark anything you have already committed to as *must pursue*, or set it to *not interested* to take it out of
   the plan.

**Why it matters**

The goal is not to submit as many applications as possible. It is to put limited staff time behind the
opportunities most likely to be won and delivered well. Three considered applications beat six rushed ones, and
seeing the collision between deadlines before it happens is what makes that choice possible.

**Tips for success**

- Enter your existing commitments first. A plan that ignores the reporting you already owe will mislead you.
- When a grant is deferred, read the hours figure. It usually tells you precisely what would have to change for
  it to fit.
- Revisit after any deadline shifts. Prioritization is a decision you remake, not one you make once.

**What's next**

With a shortlist you can actually staff, you are ready to write.""",
        "site-portfolio.webp",
        "A recommended portfolio at a set number of hours a week, with the reason beside every decision."),
    "application": (
        "Build a stronger application",
        "Work through the funder's questions with your own evidence at hand, and prepare the budget alongside.",
        "Drafts are assembled from the facts you have supplied, so what you submit stays yours — supported, "
        "specific and free of claims you cannot back up.",
        "How to prepare and strengthen your application",
        """**How to do it**

1. From a saved grant, choose **Work on application**, or open **Applications** and start a new one.
2. On **Write answers**, select a question. Add the facts that answer it, then ask for a draft built from those
   facts. Edit freely: a suggestion never replaces your text until you choose to use it.
3. Anything your records do not support is marked for attention rather than invented, so you always know what
   still needs a real answer.
4. Open **Review proposal** for a scorecard across clarity, specificity, alignment, evidence and completeness,
   with the weakest parts named and a suggested revision for each.
5. Use **Budget & narrative** to enter your cost lines. Totals are calculated for you and checked against the
   amount you are requesting, and the narrative is written from those lines.
6. Work through the verification checklist before you submit. It lists every statement a person should confirm.

**Why it matters**

Reviewers notice unsupported claims, and a vague answer is often the difference between a funded and an unfunded
application. Drafting from your own evidence keeps the application accurate and makes the gaps visible early,
while you still have time to fill them — rather than the night before the deadline.

**Tips for success**

- Add facts before asking for a draft. The quality of what comes back depends entirely on what you put in.
- Treat the review as a colleague's read, not a verdict: act on the specific gaps it names.
- Build the budget early. It often surfaces questions the narrative needs to answer.

**What's next**

A strong application still has to arrive on time.""",
        None, None),
    "timeline": (
        "Stay on track to the deadline",
        "Turn the funder's date into a plan with dates of its own, and keep the work moving.",
        "You see at a glance what is due, what is late and what is coming — and whether the remaining time is "
        "genuinely enough.",
        "How to manage deadlines and application progress",
        """**How to do it**

1. Open an application's **Timeline** tab and create a workback plan. GrantBridge places seven milestones —
   eligibility review, documents, budget, first draft, internal review, final revisions and submission — working
   backwards from the deadline.
2. Adjust how long any step should take if your process differs, and set how many days before the deadline you
   want to submit.
3. Tick milestones off as you complete them. Outstanding steps appear on your **Dashboard** under **Next steps**,
   and anything late is raised under **What needs your attention**.
4. Download the plan as a calendar file so the dates sit in your team's own calendars.
5. If the plan does not fit the time available, GrantBridge shortens it and says so, so you can decide whether to
   start now, ask for an extension, or let this round go.

**Why it matters**

Applications rarely fail because of one difficult question; they fail because the documents were requested too
late or the review never happened. A dated plan converts a distant deadline into this week's work, and makes it
obvious early — while you can still act — when there is not enough runway.

**Tips for success**

- Set the submission target a few days before the deadline. Portals are busiest and least reliable on the last
  day.
- Share the calendar file with everyone whose sign-off you need, especially for attachments you cannot produce
  yourself.
- If a plan comes back squeezed, treat that as information rather than a nuisance: it is usually right.

**What's next**

Submit, record the outcome, and bring what you learned to the next opportunity.""",
        None, None),
}

with public.shell("how-it-works"):
    public.eyebrow("how", "How it works")
    st.title("From a blank profile to a submitted application", anchor=False)
    public.lede("Six steps, in the order a grant actually happens. Most of the value is in the third one — long "
                "before anyone starts writing.")

    st.space("small")
    for n, (key, _title, *_rest) in enumerate(c.WALKTHROUGH, 1):
        title, does, helps, ask, guide, shot, shot_caption = STEPS[key]
        with st.container(key=f"how-step-{n}"):
            with st.container(key=f"how-num-{n}"):
                st.markdown(f"{n:02d}")
            st.subheader(title, anchor=False)
            st.markdown(does)
            with st.container(key=f"how-helps-{n}"):
                st.markdown(helps)
            if shot and (SHOTS / shot).exists():
                with st.container(key=f"how-shot-{n}"):
                    st.image(str(SHOTS / shot), width="stretch",
                             alt=f"A GrantBridge screen: {shot_caption}")
                    st.caption(shot_caption)
            with st.expander(ask):
                st.markdown(guide)

    public.closing(user, "how", "Ready to spend less time chasing funding?",
                   "Create your nonprofit profile and start finding opportunities worth pursuing.",
                   secondary=("Explore the interactive demo", public.TRY_FEATURES))
