"""Trust & Responsible AI — what the AI does, what code does, and what GrantBridge does not claim.

A public page: it reads no account's data. Every statement here describes a safeguard that exists in this
repository and is covered by its tests; the limitations are stated as plainly as the protections.
"""

import streamlit as st

from grantbridge import public, session

user = session.current_user()

SPLIT = [
    ("Decided by code", ":material/calculate:",
     ["Whether you meet each eligibility rule, and what is still unknown",
      "The go/no-go outcome of Should We Pursue?, from rules printed on the page",
      "Every number: budget totals, the match, the cash a grant would tie up, workback dates",
      "Which grants fit your staff hours, and the order they are scheduled in"]),
    ("Written by the AI, then checked by code", ":material/smart_toy:",
     ["Plain-language explanations of a result code has already computed",
      "Draft answers, built only from facts you entered",
      "Quoted evidence for mission fit and mission drift",
      "Conditions read out of an award notice, each with the sentence it came from"]),
]
LIMITS = [
    ("Grant coverage", "Search covers federal opportunities from Grants.gov, plus sample listings for "
                        "learning the tool. Foundation and corporate funders are not included yet."),
    ("Estimates, clearly marked", "Strategic fit is an indicator, not a judgement. Effort hours are "
                                  "assumptions you can edit. The cash projection spreads spending evenly and takes "
                                  "award terms exactly as written."),
    ("AI output varies", "Wording and ratings differ between runs. The checks around the model bound what can "
                         "go wrong; they cannot make it identical every time."),
    ("No measured time savings", "GrantBridge has not yet been evaluated with nonprofit staff, so we make no "
                                 "claim about hours saved."),
]

with public.shell("trust"):
    public.eyebrow("trust", "Trust and responsible AI")
    st.title("Code decides. The AI explains. You check the funder.", anchor=False)
    public.lede("Software that quietly guesses a deadline or invents an eligibility rule costs a small "
                "organization more than it saves. GrantBridge is built so the parts that must be right are never "
                "left to a language model.")

    st.space("small")
    for col, (title, icon, points) in zip(st.columns(2, gap="large"), SPLIT):
        with col, st.container(border=True, key=f"about-feature-{title.split()[2].lower()}", height="stretch"):
            st.markdown(f"### {icon}")
            st.markdown(f"**{title}**")
            for point in points:
                st.markdown(f"- {point}")

    st.space("medium")
    st.subheader("How information is labelled", anchor=False)
    st.markdown("Every fact on a page says where it came from, because the four are not equally trustworthy:")
    st.markdown("- **Verified by code** — a rule GrantBridge checked itself, such as an award range or a state "
                "restriction.\n"
                "- **You told us** — a self-reported fact from your profile. GrantBridge does not verify it with "
                "the IRS or anyone else; funders will.\n"
                "- **Written by AI** — always labelled as such, and checked against your records before you see it.\n"
                "- **Unknown** — information nobody has. It is never silently treated as a yes or a no, and a "
                "grant is never excluded for it.")

    st.space("medium")
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("What the AI is not allowed to do", anchor=False)
        st.markdown("- **Invent a requirement.** A funder requirement must appear in the funder's own text, or it "
                    "is relabelled as general good practice.\n"
                    "- **Invent a figure.** A number the AI writes that your records do not support is marked "
                    "`[VERIFY]`, and a missing fact becomes `[NEEDS: …]` rather than a plausible sentence.\n"
                    "- **Predict funding.** Sentences predicting an award are removed before you see them.\n"
                    "- **Follow instructions hidden in a grant.** Grant and pasted text reach the model as data; "
                    "wording aimed at an AI is flagged and never acted on.\n"
                    "- **Overturn a check.** The AI cannot change a go/no-go outcome; it only adds evidence.")
    with right:
        st.subheader("Human oversight", anchor=False)
        st.markdown("- Every recommendation shows the rule behind it, so you can disagree with it on the evidence.\n"
                    "- Unknown items are listed for a person to confirm, and your confirmation is recorded as "
                    "yours and dated.\n"
                    "- A failed hard check cannot be confirmed away: fix the profile if it is wrong.\n"
                    "- Drafts never overwrite what you wrote. A suggestion stays a suggestion until you use it.\n"
                    "- **Always confirm eligibility, deadlines, award terms, and submission requirements on the "
                    "funder's own documents.** GrantBridge is a research aid, not an authority.")

    st.space("medium")
    st.subheader("Privacy and account separation", anchor=False)
    priv, sec = st.columns(2, gap="large")
    priv.markdown("- Every record is tied to one account and checked on each read and write. One account cannot "
                  "see another's profile, grants, applications, budgets, or conversations.\n"
                  "- Email addresses and phone numbers are stripped out before any text goes to the AI model.\n"
                  "- Grants.gov receives only an opportunity id, or your search filters. It never receives your "
                  "profile.\n"
                  "- Logs record step names, timings, and token counts — never prompts, replies, or your text.")
    sec.markdown("- Passwords are stored only as salted Argon2id hashes, never in plain text.\n"
                 "- Five failed sign-ins lock an account for fifteen minutes.\n"
                 "- Sessions end on logout, after thirty idle minutes, and on refresh.\n"
                 "- The only upload GrantBridge accepts is a funder's solicitation — PDF, DOCX or TXT — when you "
                 "start an application. A file is identified by its contents rather than its name, read in memory "
                 "and not kept, and never run. Please do not upload confidential documents.\n"
                 "- Public demonstrations run on sample data and store nothing.")

    st.space("medium")
    with st.container(border=True, key="about-trust"):
        st.subheader(":material/info: What we do not claim", anchor=False)
        st.markdown("GrantBridge is in active development, and we would rather be plain about the gaps than let "
                    "you discover them. There is no independent security audit or compliance certification, no "
                    "email verification, and no per-IP rate limiting. **Please do not put confidential "
                    "information into it yet.**")
        for name, text in LIMITS:
            st.markdown(f"- **{name}.** {text}")

    public.closing(user, "trust", "See the safeguards working",
                   "The demonstration runs the real decision rules, so you can watch what GrantBridge decides and "
                   "what it refuses to assume.",
                   secondary=("Explore the interactive demo", public.TRY_FEATURES))
