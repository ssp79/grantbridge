"""About Us — why GrantBridge exists, who it is for, and what it is not.

A public page: it reads no account's data. Everything stated here is about the software in this repository. There
are no founders, customers, partnerships, testimonials, or impact figures, because there are none to report.
"""

import streamlit as st

from grantbridge import public, session

user = session.current_user()

MISSION = ("Great ideas shouldn't go unfunded because an organization lacks a dedicated grant-writing team. "
           "GrantBridge makes strategic fundraising guidance more accessible, helping small nonprofits compete for "
           "funding while staying focused on the communities they serve.")
DIFFERENT = [
    ("Opportunity discovery", "Practice listings for learning the tool, and live federal opportunities from "
     "Grants.gov, each labelled with where it came from and when it was retrieved."),
    ("Eligibility checks", "Rules checked in code against your profile, with anything missing reported as unknown "
     "rather than assumed either way."),
    ("Mission alignment", "A check for grants that would pull you away from the work you exist to do, with the "
     "funder's own words quoted as the evidence."),
    ("Organizational capacity", "The hours each application would take, scheduled against the hours your team "
     "actually has."),
    ("Financial feasibility", "What winning would cost before the money arrives: the match, the wait for "
     "reimbursement, overhead limits, and the staff the award requires."),
    ("Portfolio prioritization", "Which of the grants in front of you to pursue first, given deadlines and the "
     "hours left."),
    ("Proposal support", "Drafts built from your own facts, a review of the whole application, and a budget whose "
     "arithmetic is done in code."),
]

with public.shell("about-us"):
    public.eyebrow("aboutus", "About us")
    st.title("Helping small nonprofits compete for funding", anchor=False)
    public.lede("GrantBridge is built for organizations with no grant-writing department, where the person "
                "writing the application is also running the programme.")

    with st.container(key="about-mission"):
        st.markdown(MISSION)

    st.space("medium")
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("The problem", anchor=False)
        # The dollar signs are escaped: Streamlit reads an unescaped pair as LaTeX and sets the text as a formula.
        st.markdown("Most nonprofits are small. By the National Council of Nonprofits' count, **92% spend less than "
                    r"\$1 million a year** and **88% less than \$500,000**. For a team that size, every "
                    "application competes for the same few staff hours that also deliver the programs.")
        st.markdown("The expensive mistake is rarely a weak paragraph. It is the fortnight spent on a grant the "
                    "organization was never eligible for, three deadlines landing in the same week, or money that "
                    "quietly pulls the organization away from the people it serves. Winning can cost cash too: "
                    "some awards require a match, and many pay only after you have already spent.")
    with right:
        st.subheader("Why GrantBridge exists", anchor=False)
        st.markdown("Generic writing assistants start at the drafting step, by which point the expensive decision "
                    "has already been made. GrantBridge starts earlier — at the decision — and keeps the evidence "
                    "attached all the way to submission.")
        st.markdown("Its guiding rule is that **code decides and the AI explains**. Every yes-or-no judgement, "
                    "number, and date is computed in Python from rules you can read on the page. The model writes "
                    "and interprets; it never casts the deciding vote, and code checks what it wrote before you "
                    "see it.")

    st.space("medium")
    public.eyebrow("combination", "What makes it different")
    st.subheader("Smarter grant decisions, from discovery to submission.", anchor=False)
    st.markdown("Most grant tools help you find opportunities or write applications. GrantBridge connects the "
                "steps in between — helping your team evaluate eligibility, assess financial and staffing "
                "capacity, prioritize opportunities, and focus on funding that's worth pursuing.")
    for row in (DIFFERENT[:4], DIFFERENT[4:]):
        for col, (name, text) in zip(st.columns(len(row), gap="medium"), row):
            with col, st.container(border=True, key=f"about-feature-{name.split()[0].lower()}", height="stretch"):
                st.markdown(f"**{name}**")
                st.caption(text)

    st.space("medium")
    who, prototype = st.columns(2, gap="large")
    with who:
        st.subheader("Who it is for", anchor=False)
        st.markdown("- Small U.S. nonprofits without a dedicated grant writer.\n"
                    "- Executive directors and program staff who write applications between other duties.\n"
                    "- Boards and finance volunteers who need the reasoning behind a go or no-go decision.\n"
                    "- Anyone who has to explain to a board *why* a grant was not pursued.")
    with prototype:
        st.subheader("Where GrantBridge is today", anchor=False)
        st.markdown("GrantBridge is in active development. The workflow described on this site is built and "
                    "working, and we would rather say plainly what is not finished than imply otherwise: there is "
                    "no independent security audit yet, so it is not the place for confidential information.")
        st.markdown("Grant coverage is federal opportunities from Grants.gov, with foundation sources next. The "
                    "full picture of what is implemented, what is assumed, and what you should verify yourself is "
                    "on the Trust & Responsible AI page.")

    public.closing(user, "aboutus", "See it decide for yourself",
                   "Work through a real assessment on sample opportunities — no account required.",
                   secondary=("Explore the interactive demo", public.TRY_FEATURES))
