"""Generate the sample PDFs used by demo mode (requires reportlab: the backend dev extra).

Writes into backend/demo_docs/, which is baked into the backend Docker image. The content is
fictional and written for this project.

    backend/.venv/bin/python samples/make_sample_pdf.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "demo_docs"

DOCUMENTS: dict[str, list[tuple[str, list[str]]]] = {
    "remote-work-policy.pdf": [
        ("Remote Work Policy 2026", [
            "This policy describes how employees of Northwind Labs, a fictional company, may work "
            "remotely. It applies to all full-time and part-time staff and takes effect on "
            "1 March 2026.",
            "The goal of the policy is to support flexible work while keeping collaboration strong.",
        ]),
        ("Eligibility and Schedules", [
            "Employees become eligible for remote work after completing a 90-day onboarding period.",
            "Staff may work remotely up to three days per week. Tuesdays and Thursdays are anchor "
            "days on which all team members are expected in the office.",
        ]),
        ("Equipment and Expenses", [
            "Northwind provides a laptop and a one-time home office stipend of 750 US dollars.",
            "Internet costs are reimbursed up to 60 US dollars per month with a valid receipt.",
        ]),
        ("Security Requirements", [
            "Remote employees must use the company VPN and enable full-disk encryption.",
            "Public Wi-Fi may only be used together with the VPN. Lost devices must be reported to "
            "IT security within 24 hours.",
        ]),
    ],
    "solar-energy-primer.pdf": [
        ("Solar Energy Primer", [
            "This primer is a short introduction to residential solar power for homeowners who "
            "are considering an installation.",
            "Photovoltaic cells convert sunlight directly into electricity using semiconductor "
            "materials, most commonly crystalline silicon.",
        ]),
        ("Panel Types and Efficiency", [
            "Monocrystalline silicon panels typically convert 20 to 23 percent of sunlight into "
            "electricity. Polycrystalline panels are cheaper but reach about 15 to 17 percent.",
            "Thin-film panels are lightweight and flexible but usually below 13 percent "
            "efficiency, so they need more roof area for the same output.",
        ]),
        ("Inverters", [
            "Panels produce direct current, which an inverter converts to alternating current for "
            "the home. String inverters serve a whole array; microinverters sit behind each panel "
            "and limit losses when part of the roof is shaded.",
        ]),
        ("Battery Storage", [
            "Lithium iron phosphate batteries offer roughly 6000 charge cycles and are a common "
            "choice for home storage because of their safety and long life.",
            "A typical household battery stores 10 to 15 kilowatt-hours, enough to cover evening "
            "use after a sunny day.",
        ]),
        ("Costs and Payback", [
            "The payback period depends on electricity prices, sunlight hours and installation "
            "cost. In sunny regions with high electricity prices it is often between six and ten "
            "years.",
            "Panels usually carry a 25-year performance warranty and lose about 0.5 percent of "
            "output per year.",
        ]),
    ],
}


def build(path: Path, pages: list[tuple[str, list[str]]]) -> None:
    styles = getSampleStyleSheet()
    story = []
    for i, (title, paras) in enumerate(pages):
        story.append(Paragraph(title, styles["Heading1"]))
        for p in paras:
            story += [Paragraph(p, styles["BodyText"]), Spacer(1, 8)]
        if i < len(pages) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(str(path), pagesize=letter, title=path.stem).build(story)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCUMENTS.items():
        build(OUT_DIR / name, pages)
        print(f"Wrote {OUT_DIR / name}")


if __name__ == "__main__":
    main()
