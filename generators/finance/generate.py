#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "deltalake==1.2.1",
#   "pyarrow==21.0.0",
#   "pypdf==6.1.1",
#   "reportlab==4.4.4",
#   "sqlglot==27.28.1",
# ]
# ///
"""Generate and validate the deterministic orthopedics finance reference data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import sqlglot
from deltalake import DeltaTable, write_deltalake
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

SEED = 20260923
ROW_COUNT = 3_000
GENERATED_AT = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
GENERATED_AT_MS = int(GENERATED_AT.timestamp() * 1_000)
CLASSES = (
    "vendor_invoice",
    "purchase_order",
    "sales_contract_pricing_agreement",
    "quarterly_financial_statement",
    "other",
)
ROWS_PER_CLASS = 5
MONEY = Decimal("0.01")
RATE = Decimal("0.0001")

TXN_FIELDS = (
    "transaction_id",
    "order_id",
    "sale_date",
    "posting_timestamp",
    "customer_id",
    "customer_name",
    "customer_type",
    "facility_state",
    "sales_region",
    "sales_rep_id",
    "product_sku",
    "product_family",
    "procedure_category",
    "units",
    "unit_price",
    "gross_sales",
    "discount_pct",
    "discount_amount",
    "net_sales",
    "cost_of_goods",
    "gross_margin",
    "currency",
    "sales_channel",
    "contract_id",
    "purchase_order_number",
    "invoice_number",
    "payment_status",
    "source_updated_at",
)

CUSTOMERS = (
    ("CUS-001", "Atlantic Ortho Alliance", "IDN", "PA", "Northeast", 13),
    ("CUS-002", "Hudson Valley Surgical Center", "ASC", "NY", "Northeast", 8),
    (
        "CUS-003",
        "Great Lakes University Hospital",
        "Academic Medical Center",
        "OH",
        "Midwest",
        12,
    ),
    ("CUS-004", "Blue Ridge Joint Institute", "Hospital", "NC", "Southeast", 9),
    ("CUS-005", "Lone Star Orthopedic Network", "IDN", "TX", "South Central", 15),
    ("CUS-006", "Pacific Motion Surgery Partners", "ASC", "CA", "West", 10),
    ("CUS-007", "Front Range Medical Center", "Hospital", "CO", "Mountain", 7),
    ("CUS-008", "Gulf Coast Trauma Hospital", "Hospital", "FL", "Southeast", 7),
    ("CUS-009", "Northwest Specialty Distribution", "Distributor", "WA", "West", 5),
    ("CUS-010", "Prairie Orthopedics Cooperative", "IDN", "IL", "Midwest", 8),
    ("CUS-011", "Desert Ridge Ambulatory Surgery", "ASC", "AZ", "Mountain", 4),
    ("CUS-012", "New England Sports Medicine", "Hospital", "MA", "Northeast", 6),
)

PRODUCTS = (
    (
        "TRI-KNEE-PS-05",
        "Triathlon Knee",
        "Total knee arthroplasty",
        Decimal("4825.00"),
        Decimal("2540.00"),
        18,
    ),
    (
        "TRI-KNEE-CR-04",
        "Triathlon Knee",
        "Total knee arthroplasty",
        Decimal("4380.00"),
        Decimal("2310.00"),
        16,
    ),
    (
        "ACC-HIP-CUP-56",
        "Acetabular System",
        "Total hip arthroplasty",
        Decimal("2975.00"),
        Decimal("1488.00"),
        14,
    ),
    (
        "ACC-HIP-LIN-36",
        "Acetabular System",
        "Total hip arthroplasty",
        Decimal("1180.00"),
        Decimal("530.00"),
        12,
    ),
    (
        "REV-FEM-STEM-12",
        "Revision Hip",
        "Revision arthroplasty",
        Decimal("6420.00"),
        Decimal("3495.00"),
        8,
    ),
    (
        "MAKO-KNEE-KIT",
        "Robotic Procedure Kit",
        "Robotic-assisted knee",
        Decimal("1640.00"),
        Decimal("690.00"),
        16,
    ),
    (
        "MAKO-HIP-KIT",
        "Robotic Procedure Kit",
        "Robotic-assisted hip",
        Decimal("1495.00"),
        Decimal("625.00"),
        11,
    ),
    (
        "SOM-PLATE-8H",
        "Trauma Plating",
        "Trauma fixation",
        Decimal("875.00"),
        Decimal("365.00"),
        9,
    ),
    (
        "SOM-SCREW-45",
        "Trauma Plating",
        "Trauma fixation",
        Decimal("146.00"),
        Decimal("42.00"),
        7,
    ),
    (
        "SPN-CAGE-LORD",
        "Spine Interbody",
        "Lumbar fusion",
        Decimal("5260.00"),
        Decimal("2735.00"),
        6,
    ),
)

VENDORS = (
    "SterilePak Medical Logistics",
    "Titanium Alloy Works",
    "Precision Polymer Components",
    "NorthStar Surgical Freight",
    "MedClean Validation Services",
)


def weighted_choice(rng: random.Random, values: Iterable[tuple[Any, int]]) -> Any:
    choices = list(values)
    return rng.choices(
        [value for value, _ in choices], weights=[weight for _, weight in choices], k=1
    )[0]


def dollars(value: Decimal) -> str:
    return f"${value:,.2f}"


def wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if len(" ".join(current + [word])) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


class FinancePdf:
    """Small deterministic canvas helper with deliberately varied layouts."""

    def __init__(self, path: Path, title: str, accent: colors.Color, variant: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf = canvas.Canvas(
            str(path),
            pagesize=letter,
            pageCompression=1,
            invariant=1,
            pdfVersion=(1, 4),
        )
        self.title = title
        self.accent = accent
        self.variant = variant
        self.page = 0
        self.pdf.setTitle(title)
        self.pdf.setAuthor("Synthetic Stryker Databricks Workshop")
        self.new_page()

    def new_page(self) -> None:
        if self.page:
            self.footer()
            self.pdf.showPage()
        self.page += 1
        if self.variant % 2:
            self.pdf.setFillColor(self.accent)
            self.pdf.rect(0, 738, 612, 54, fill=1, stroke=0)
            self.pdf.setFillColor(colors.white)
            self.pdf.setFont("Helvetica-Bold", 16)
            self.pdf.drawString(36, 758, self.title[:66])
        else:
            self.pdf.setFillColor(colors.black)
            self.pdf.setFont("Helvetica-Bold", 17)
            self.pdf.drawString(42, 757, self.title[:64])
            self.pdf.setStrokeColor(self.accent)
            self.pdf.setLineWidth(3)
            self.pdf.line(42, 744, 570, 744)
        self.y = 714

    def footer(self) -> None:
        self.pdf.setFillColor(colors.HexColor("#5B6573"))
        self.pdf.setFont("Helvetica", 7)
        self.pdf.drawString(
            40, 24, "Synthetic workshop document — no real company or patient data"
        )
        self.pdf.drawRightString(570, 24, f"Page {self.page}")

    def heading(self, text: str) -> None:
        self.pdf.setFillColor(self.accent)
        self.pdf.setFont("Helvetica-Bold", 11)
        self.pdf.drawString(42, self.y, text.upper())
        self.y -= 18

    def text(
        self, text: str, *, size: int = 9, indent: int = 0, leading: int = 12
    ) -> None:
        self.pdf.setFillColor(colors.HexColor("#20252B"))
        self.pdf.setFont("Helvetica", size)
        for line in wrap(text, max(38, int((510 - indent) / (size * 0.52)))):
            if self.y < 54:
                self.new_page()
            self.pdf.drawString(42 + indent, self.y, line)
            self.y -= leading
        self.y -= 3

    def kv(self, pairs: list[tuple[str, str]], columns: int = 2) -> None:
        col_width = 258 if columns == 2 else 172
        row_height = 30
        for start in range(0, len(pairs), columns):
            if self.y < 70:
                self.new_page()
            row = pairs[start : start + columns]
            for col, (label, value) in enumerate(row):
                x = 42 + col * col_width
                self.pdf.setFillColor(colors.HexColor("#667085"))
                self.pdf.setFont("Helvetica-Bold", 7)
                self.pdf.drawString(x, self.y, label.upper())
                self.pdf.setFillColor(colors.black)
                self.pdf.setFont("Helvetica", 9)
                self.pdf.drawString(x, self.y - 13, value[:40])
            self.y -= row_height
        self.y -= 4

    def table(
        self, headers: list[str], rows: list[list[str]], widths: list[int]
    ) -> None:
        font_size = 7
        height = 22
        x0 = 42
        if self.y < 100:
            self.new_page()
        self.pdf.setFillColor(self.accent)
        self.pdf.rect(x0, self.y - 15, sum(widths), 20, fill=1, stroke=0)
        self.pdf.setFillColor(colors.white)
        self.pdf.setFont("Helvetica-Bold", font_size)
        x = x0
        for header, width in zip(headers, widths):
            self.pdf.drawString(x + 3, self.y - 8, header[: int(width / 4.3)])
            x += width
        self.y -= 19
        for row_no, row in enumerate(rows):
            if self.y < 58:
                self.new_page()
            if row_no % 2 == 0:
                self.pdf.setFillColor(colors.HexColor("#F2F4F7"))
                self.pdf.rect(x0, self.y - 16, sum(widths), height, fill=1, stroke=0)
            self.pdf.setFillColor(colors.black)
            self.pdf.setFont("Helvetica", font_size)
            x = x0
            for value, width in zip(row, widths):
                max_chars = max(5, int(width / 4.0))
                display = (
                    value
                    if stringWidth(value, "Helvetica", font_size) < width - 6
                    else value[: max_chars - 1] + "…"
                )
                self.pdf.drawString(x + 3, self.y - 9, display)
                x += width
            self.y -= height
        self.y -= 8

    def finish(self) -> None:
        self.footer()
        self.pdf.save()


def invoice_pdf(path: Path, index: int, rng: random.Random) -> dict[str, str]:
    vendor = VENDORS[index]
    invoice_no = f"{['INV', 'BILL', 'ACCT', 'CHG', 'STM'][index]}-{260900 + index * 17}"
    issue = date(2026, 7, 8) + timedelta(days=index * 6)
    subtotal = Decimal(str(18340 + index * 9327 + rng.randint(100, 900))).quantize(
        MONEY
    )
    freight = Decimal(str(285 + index * 44)).quantize(MONEY)
    tax = (
        subtotal * Decimal("0.0625") if index in (1, 4) else Decimal("0.00")
    ).quantize(MONEY)
    total = subtotal + freight + tax
    titles = (
        "Tax Invoice",
        "Statement of Goods Supplied",
        "Commercial Account",
        "Charges & Delivery Detail",
        "Vendor Billing Statement",
    )
    doc = FinancePdf(path, titles[index], colors.HexColor("#175CD3"), index)
    doc.text(
        f"{vendor} | Supplier account SP-{8041 + index}. Payment correspondence: accounts@{vendor.split()[0].lower()}.example"
    )
    doc.kv(
        [
            ("Document number", invoice_no),
            ("Issue date", issue.isoformat()),
            (
                "Terms",
                ["Net 30", "2% 10 / Net 45", "Net 60", "Due on receipt", "Net 30"][
                    index
                ],
            ),
            (
                "Due date",
                (issue + timedelta(days=[30, 45, 60, 10, 30][index])).isoformat(),
            ),
            ("Customer PO", f"PO-STR-26-{4100 + index * 37}"),
            ("Currency", "USD"),
        ]
    )
    doc.heading("Bill to / delivery")
    doc.text(
        "Stryker Orthopaedics Finance Operations, 325 Corporate Drive, Mahwah, NJ 07430. Deliver to the receiving location printed on the referenced purchase order; include lot and sterilization certificates."
    )
    lines = [
        [
            "TA-6AL4V",
            "Implant-grade titanium blanks",
            str(18 + index * 3),
            dollars(Decimal("642.00")),
            dollars(subtotal * Decimal("0.54")),
        ],
        [
            "VAL-SVC",
            "Sterility validation service",
            "1",
            dollars(Decimal("4860.00")),
            dollars(subtotal * Decimal("0.26")),
        ],
        [
            "COLD-LOG",
            "Controlled transport / logger",
            str(2 + index),
            dollars(Decimal("435.00")),
            dollars(subtotal * Decimal("0.20")),
        ],
    ]
    doc.table(
        ["Item", "Description", "Qty", "Unit price", "Line amount"],
        lines,
        [58, 195, 42, 75, 88],
    )
    doc.kv(
        [
            ("Subtotal", dollars(subtotal)),
            ("Tax", dollars(tax)),
            ("Freight", dollars(freight)),
            ("Amount due", dollars(total)),
        ]
    )
    doc.new_page()
    doc.heading("Remittance and compliance detail")
    doc.text(
        f"Remit {dollars(total)} quoting {invoice_no}. ACH routing ending 0198; beneficiary name must match {vendor}. This document references PO-STR-26-{4100 + index * 37}, but it does not authorize new purchasing activity."
    )
    doc.text(
        "Each shipped component is represented as non-patient-specific, medical-device manufacturing material. Supplier certifies traceability to the listed heat or lot records and compliance with agreed quality controls."
    )
    doc.heading("Receiving reconciliation")
    doc.table(
        ["Packing record", "Lot / service ref", "Received", "Exception"],
        [
            [
                f"PK-{7001 + index}",
                f"LOT-TI-{940 + index}",
                issue.isoformat(),
                "None noted",
            ],
            [
                f"PK-{7021 + index}",
                f"VAL-{20260 + index}",
                (issue + timedelta(days=1)).isoformat(),
                "Certificate attached",
            ],
        ],
        [95, 135, 95, 132],
    )
    doc.text(
        "Questions about price variance should be directed to supplier resolution within ten business days. Late-payment language is governed by the master supplier agreement and is not a purchase commitment."
    )
    doc.finish()
    return {"document_subtype": titles[index], "document_id": invoice_no}


def purchase_order_pdf(path: Path, index: int, rng: random.Random) -> dict[str, str]:
    po = f"PO-STR-26-{5100 + index * 29}"
    order_date = date(2026, 8, 3) + timedelta(days=index * 4)
    vendor = VENDORS[(index + 2) % len(VENDORS)]
    total = Decimal(str(24500 + index * 17300 + rng.randint(200, 1800))).quantize(MONEY)
    titles = (
        "Purchase Order",
        "Procurement Release",
        "Supply Authorization",
        "Blanket Order Call-Off",
        "Materials Commitment",
    )
    doc = FinancePdf(path, titles[index], colors.HexColor("#067647"), index + 1)
    doc.text(
        "STRYKER ORTHOPAEDICS — Strategic Sourcing | This numbered document authorizes delivery subject to the commercial and quality terms below."
    )
    doc.kv(
        [
            ("Order / release", po),
            ("Order date", order_date.isoformat()),
            ("Supplier", vendor),
            (
                "Buyer",
                ["M. Reyes", "J. Patel", "A. Carter", "L. Wong", "D. Brooks"][index],
            ),
            (
                "Requested delivery",
                (order_date + timedelta(days=21 + index * 3)).isoformat(),
            ),
            ("Payment terms", "Net 45 after acceptance"),
            (
                "Ship to",
                [
                    "Mahwah NJ",
                    "Kalamazoo MI",
                    "Flower Mound TX",
                    "Phoenix AZ",
                    "Salt Lake City UT",
                ][index],
            ),
            ("Currency", "USD"),
        ]
    )
    rows = [
        [
            "1",
            "ASTM F136 titanium rod / implant grade",
            str(24 + index * 5),
            dollars(total * Decimal("0.021")),
            dollars(total * Decimal("0.50")),
        ],
        [
            "2",
            "UHMWPE resin, validated medical grade",
            str(12 + index * 2),
            dollars(total * Decimal("0.031")),
            dollars(total * Decimal("0.31")),
        ],
        [
            "3",
            "Inspection and material certification",
            "1",
            dollars(total * Decimal("0.19")),
            dollars(total * Decimal("0.19")),
        ],
    ]
    doc.table(
        ["Line", "Ordered material / service", "Qty", "Unit price", "Extended"],
        rows,
        [38, 215, 42, 78, 86],
    )
    doc.kv([("Order total", dollars(total)), ("Freight", "FOB destination / prepaid")])
    doc.text(
        "Do not invoice before shipment. Supplier invoices must quote the order number and line. Quantity tolerance is zero unless the buyer approves a written deviation."
    )
    doc.new_page()
    doc.heading("Delivery, quality, and acceptance")
    doc.text(
        "All lots require certificate of analysis, country-of-origin statement, and full material traceability. Change notification is required before modifying a validated process, source, facility, or formulation."
    )
    doc.text(
        "Receipt at the dock does not constitute acceptance. Stryker may inspect or reject nonconforming goods. Replacement, containment, and expedited freight caused by nonconformance remain the supplier's responsibility."
    )
    doc.heading("Commercial controls")
    doc.table(
        ["Control", "Requirement", "Owner"],
        [
            [
                "Invoice match",
                "Three-way match: order, receipt, invoice",
                "Accounts payable",
            ],
            ["Packing slip", f"Print {po} and line numbers", "Supplier"],
            [
                "Forecast",
                "Planning signal only; not authorization",
                "Strategic sourcing",
            ],
            ["Changes", "Written buyer revision required", "Buyer"],
        ],
        [100, 260, 98],
    )
    doc.text(
        "The master purchasing agreement is incorporated by reference. Conflicting supplier acknowledgements do not amend this order. Send acknowledgements within two business days."
    )
    doc.finish()
    return {"document_subtype": titles[index], "document_id": po}


def contract_pdf(path: Path, index: int, rng: random.Random) -> dict[str, str]:
    agreement = f"AGR-ORTHO-26-{310 + index * 7}"
    customer = CUSTOMERS[[0, 2, 4, 5, 9][index]][1]
    effective = date(2026, 1, 1) + timedelta(days=index * 31)
    titles = (
        "Implant Pricing Agreement",
        "Commercial Terms Addendum",
        "Enterprise Supply Schedule",
        "Orthopaedic Portfolio Agreement",
        "Procedure Pricing Exhibit",
    )
    doc = FinancePdf(path, titles[index], colors.HexColor("#7A5AF8"), index)
    doc.text(
        f"Agreement between Stryker Orthopaedics (Supplier) and {customer} (Customer). Confidential commercial terms; no patient information is included."
    )
    doc.kv(
        [
            ("Agreement ID", agreement),
            ("Effective date", effective.isoformat()),
            (
                "Expiration date",
                (effective.replace(year=2027) - timedelta(days=1)).isoformat(),
            ),
            ("Pricing territory", "United States"),
            (
                "Customer account",
                f"{CUSTOMERS[[0, 2, 4, 5, 9][index]][0]} / affiliated sites",
            ),
            ("Currency", "USD"),
        ]
    )
    doc.heading("Covered portfolio and net pricing")
    discounts = [
        Decimal("0.18"),
        Decimal("0.22"),
        Decimal("0.15"),
        Decimal("0.20"),
        Decimal("0.17"),
    ]
    discount = discounts[index]
    rows = []
    for product in PRODUCTS[:5]:
        list_price = product[3]
        net = (list_price * (Decimal("1.00") - discount)).quantize(MONEY)
        rows.append(
            [
                product[0],
                product[1],
                dollars(list_price),
                f"{discount * 100:.1f}%",
                dollars(net),
            ]
        )
    doc.table(
        ["SKU", "Portfolio", "List", "Discount", "Contract net"],
        rows,
        [92, 145, 70, 67, 85],
    )
    commitment = 130 + index * 35
    doc.text(
        f"Customer commits to a minimum of {commitment} primary joint procedures during the term. The commitment is measured across participating facilities; it is not a take-or-pay purchase order."
    )
    doc.new_page()
    doc.heading("Rebates, review, and exclusions")
    doc.text(
        f"An incremental {2 + index % 2}% quarterly rebate applies after {commitment // 4} qualifying procedures in a calendar quarter. Returns, no-charge evaluation product, freight, tax, and capital equipment do not count toward the threshold."
    )
    doc.text(
        "Prices may be reviewed for documented changes in tariffs, raw-material indices, or law. Any price change requires a signed amendment; invoices and purchase orders alone do not modify this schedule."
    )
    doc.heading("Administrative terms")
    doc.table(
        ["Topic", "Agreed term"],
        [
            ["Reporting", "Quarterly utilization statement within 30 days"],
            ["Payment", "Net 45 from undisputed invoice date"],
            ["Confidentiality", "Pricing restricted to authorized personnel"],
            [
                "Governing law",
                ["New Jersey", "Ohio", "Texas", "California", "Illinois"][index],
            ],
            ["Termination", "60 days for uncured material breach"],
        ],
        [125, 333],
    )
    doc.text(
        f"Authorized signature record: Supplier commercial operations / Customer supply chain. Reference {agreement} on eligible sales transactions and rebate reports."
    )
    doc.finish()
    return {"document_subtype": titles[index], "document_id": agreement}


def statement_pdf(path: Path, index: int, rng: random.Random) -> dict[str, str]:
    quarters = (
        ("Q2 2026", "2026-06-30"),
        ("Q1 2026", "2026-03-31"),
        ("Q4 2025", "2025-12-31"),
        ("Q3 2025", "2025-09-30"),
        ("Q2 2025", "2025-06-30"),
    )
    period, end_date = quarters[index]
    revenue = Decimal(
        str(955_000_000 - index * 31_000_000 + rng.randint(1_000_000, 8_000_000))
    )
    cogs = (revenue * Decimal("0.362")).quantize(MONEY)
    gross = revenue - cogs
    op_income = (revenue * Decimal("0.214")).quantize(MONEY)
    net_income = (revenue * Decimal("0.154")).quantize(MONEY)
    titles = (
        "Quarterly Financial Statement",
        "Management Results — Quarter End",
        "Condensed Segment Accounts",
        "Quarterly Performance Book",
        "Form 10-Q Segment Extract",
    )
    doc = FinancePdf(path, titles[index], colors.HexColor("#B54708"), index + 1)
    doc.text(
        "Stryker Orthopaedics reporting segment | Unaudited synthetic management information | Amounts in USD millions except per-procedure data."
    )
    doc.kv(
        [
            ("Reporting period", period),
            ("Period ended", end_date),
            ("Entity", "Stryker Orthopaedics (synthetic segment)"),
            ("Basis", "Management reporting / unaudited"),
        ]
    )
    doc.heading("Condensed statement of operations")
    current = lambda value: f"{value / Decimal(1000000):,.1f}"
    prior_revenue = revenue * Decimal("0.962")
    rows = [
        ["Net sales", current(revenue), current(prior_revenue)],
        ["Cost of sales", current(cogs), current(prior_revenue * Decimal("0.368"))],
        ["Gross profit", current(gross), current(prior_revenue * Decimal("0.632"))],
        [
            "Research & development",
            current(revenue * Decimal("0.071")),
            current(prior_revenue * Decimal("0.069")),
        ],
        [
            "Selling / administrative",
            current(revenue * Decimal("0.353")),
            current(prior_revenue * Decimal("0.359")),
        ],
        [
            "Operating income",
            current(op_income),
            current(prior_revenue * Decimal("0.204")),
        ],
        ["Net income", current(net_income), current(prior_revenue * Decimal("0.146"))],
    ]
    doc.table(
        ["USD millions", "Current quarter", "Prior-year quarter"], rows, [220, 119, 119]
    )
    doc.text(
        "Net sales reflect procedure volume and contractual pricing. The Northeast experienced delayed robotic procedure-kit availability in April, partially offset by recovery shipments in June."
    )
    doc.new_page()
    doc.heading("Balance sheet and operating indicators")
    cash = revenue * Decimal("0.118")
    doc.table(
        ["Indicator", "Quarter end", "Comment"],
        [
            ["Cash and equivalents", current(cash), "Segment allocation"],
            ["Accounts receivable", current(revenue * Decimal("0.284")), "DSO 51 days"],
            ["Inventory", current(revenue * Decimal("0.201")), "Safety stock rebuilt"],
            [
                "Capital expenditure",
                current(revenue * Decimal("0.042")),
                "Manufacturing cells",
            ],
            [
                "Gross margin",
                f"{(gross / revenue) * 100:.1f}%",
                "Mix and discount pressure",
            ],
        ],
        [170, 105, 183],
    )
    doc.heading("Management discussion")
    doc.text(
        "Reconstructive implant demand remained resilient. Sales through ambulatory surgery centers grew faster than hospital channels, while distributor demand was intentionally moderated to normalize inventory."
    )
    doc.text(
        "This packet contains forward-looking assumptions and is not a vendor invoice, purchase authorization, or customer pricing offer. Totals may not add due to rounding."
    )
    doc.finish()
    return {
        "document_subtype": titles[index],
        "document_id": f"FIN-{period.replace(' ', '-')}-ORTHO",
    }


def other_pdf(path: Path, index: int, rng: random.Random) -> dict[str, str]:
    subtypes = (
        "Supplier Credit Memorandum",
        "Field Expense Report",
        "Customer Remittance Advice",
        "Bank Reconciliation",
        "Capital Expenditure Request",
    )
    ids = ("CM-772041", "EXP-2608-114", "REM-900184", "REC-0726-03", "CAPEX-26-088")
    title = subtypes[index]
    doc_id = ids[index]
    amount = Decimal(str([12_480, 3_842, 184_225, 96_331, 875_000][index])) + Decimal(
        str(rng.randint(1, 95))
    )
    doc = FinancePdf(path, title, colors.HexColor("#C11574"), index)
    doc.text(
        "Orthopaedics Finance Operations | Supporting finance record intentionally outside the primary four-class document taxonomy."
    )
    doc.kv(
        [
            ("Reference", doc_id),
            (
                "Document date",
                (date(2026, 7, 11) + timedelta(days=index * 9)).isoformat(),
            ),
            ("Amount", dollars(amount)),
            ("Currency", "USD"),
        ]
    )
    if index == 0:
        doc.text(
            "Issued by Precision Polymer Components to Stryker Orthopaedics for returned nonconforming resin. Apply against vendor invoice INV-260881 and purchase order PO-STR-26-4027; this is a reduction, not an amount due."
        )
        rows = [
            ["RET-UHMWPE", "Returned material / lot PP-442", "-8", dollars(amount)],
            [
                "QA-HOLD",
                "Quality containment allowance",
                "1",
                dollars(Decimal("1250.00")),
            ],
        ]
        doc.table(["Reference", "Reason", "Qty", "Credit"], rows, [95, 235, 50, 78])
    elif index == 1:
        doc.text(
            "Employee: Jordan Ellis | Territory: Northeast | Cost center: ORTHO-FIELD-210. Expenses support surgeon education and field inventory review; no patient-identifying information is included."
        )
        doc.table(
            ["Date", "Category", "Business purpose", "Amount"],
            [
                ["2026-08-02", "Travel", "Regional inventory review", "$1,184.50"],
                ["2026-08-03", "Lodging", "Surgeon education program", "$1,625.00"],
                ["2026-08-04", "Meals", "Field team meeting", "$412.75"],
            ],
            [75, 100, 205, 78],
        )
    elif index == 2:
        doc.text(
            "Received from Atlantic Ortho Alliance. The payment settles multiple customer invoices and includes one short-pay under active pricing-dispute review."
        )
        doc.table(
            ["Invoice", "Invoice date", "Gross", "Adjustment", "Applied"],
            [
                ["SI-880041", "2026-06-18", "$92,114.00", "$0.00", "$92,114.00"],
                ["SI-881220", "2026-06-25", "$94,086.00", "-$1,975.00", "$92,111.00"],
            ],
            [90, 85, 90, 90, 103],
        )
    elif index == 3:
        doc.text(
            "Operating account ending 1932. Reconciliation bridges the bank statement to the finance ledger after outstanding checks, deposits in transit, and fee adjustments."
        )
        doc.table(
            ["Reconciliation item", "Ledger ref", "Increase", "Decrease"],
            [
                ["Statement balance", "BANK-0731", dollars(amount), "$0.00"],
                ["Deposits in transit", "DEP-0731-4", "$42,870.00", "$0.00"],
                ["Outstanding supplier checks", "AP-BATCH-772", "$0.00", "$31,204.00"],
                ["Bank service fee", "JE-260731-19", "$0.00", "$245.00"],
            ],
            [190, 105, 82, 82],
        )
    else:
        doc.text(
            "Requesting function: Orthopaedics manufacturing. Proposal: automated implant inspection cell with validated vision system. Approval of this request does not authorize a supplier to ship or invoice."
        )
        doc.table(
            ["Cost component", "Estimate", "Useful life"],
            [
                ["Inspection equipment", "$620,000.00", "7 years"],
                ["Validation / integration", "$180,000.00", "5 years"],
                ["Facility preparation", "$75,000.00", "10 years"],
            ],
            [235, 105, 118],
        )
    doc.new_page()
    doc.heading("Review, support, and approval trail")
    doc.text(
        "Prepared for synthetic workshop use. Supporting references intentionally contain terms such as invoice, order, pricing, quarter, and payment so a classifier must consider the document's purpose rather than isolated keywords."
    )
    doc.table(
        ["Role", "Reviewer", "Status", "Date"],
        [
            [
                "Preparer",
                ["A. Kim", "J. Ellis", "R. Shah", "M. Costa", "K. Diaz"][index],
                "Submitted",
                "2026-08-19",
            ],
            ["Finance", "Orthopaedics controller", "Reviewed", "2026-08-20"],
            ["Compliance", "Finance operations", "No exception", "2026-08-21"],
        ],
        [95, 170, 105, 88],
    )
    doc.text(
        "Retain this record with the referenced ledger support. It is not a sales contract, purchase order, quarterly financial statement, or vendor invoice."
    )
    doc.finish()
    return {"document_subtype": title, "document_id": doc_id}


PDF_BUILDERS = {
    "vendor_invoice": invoice_pdf,
    "purchase_order": purchase_order_pdf,
    "sales_contract_pricing_agreement": contract_pdf,
    "quarterly_financial_statement": statement_pdf,
    "other": other_pdf,
}


def generate_pdfs(output_root: Path) -> None:
    documents = output_root / "documents"
    if documents.exists():
        for class_name in CLASSES:
            shutil.rmtree(documents / class_name, ignore_errors=True)
        for generated_file in (documents / "document_manifest.csv",):
            generated_file.unlink(missing_ok=True)
    documents.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for class_no, class_name in enumerate(CLASSES):
        for index in range(ROWS_PER_CLASS):
            rng = random.Random(SEED + class_no * 100 + index)
            filename = f"{class_name}_{index + 1:02d}.pdf"
            relative_path = Path(class_name) / filename
            metadata = PDF_BUILDERS[class_name](documents / relative_path, index, rng)
            manifest.append(
                {
                    "file_path": relative_path.as_posix(),
                    "document_id": metadata["document_id"],
                    "expected_class": class_name,
                    "document_subtype": metadata["document_subtype"],
                    "page_count": "2",
                    "language": "en",
                }
            )
    with (documents / "document_manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=tuple(manifest[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(manifest)


def generate_transactions() -> list[dict[str, Any]]:
    rng = random.Random(SEED + 50_000)
    rows: list[dict[str, Any]] = []
    start = date(2025, 10, 1)
    customer_weighted = [(customer, customer[-1]) for customer in CUSTOMERS]
    product_weighted = [(product, product[-1]) for product in PRODUCTS]
    for i in range(ROW_COUNT):
        customer = weighted_choice(rng, customer_weighted)
        product = weighted_choice(rng, product_weighted)
        day_offset = int(rng.triangular(0, 272, 205))
        sale_date = start + timedelta(days=day_offset)
        units = rng.choices([1, 2, 3, 4, 5, 8], weights=[42, 28, 14, 8, 5, 3], k=1)[0]
        base_discount = {
            "IDN": Decimal("0.19"),
            "Academic Medical Center": Decimal("0.17"),
            "Hospital": Decimal("0.13"),
            "ASC": Decimal("0.11"),
            "Distributor": Decimal("0.24"),
        }[customer[2]]
        if customer[4] == "Northeast" and date(2026, 4, 1) <= sale_date <= date(
            2026, 5, 20
        ):
            # A supply recovery concession creates an explainable regional margin dip.
            base_discount += Decimal("0.035")
        discount_pct = (
            base_discount + Decimal(str(rng.choice([-0.01, 0, 0, 0.005, 0.01])))
        ).quantize(RATE)
        price_jitter = Decimal(str(rng.choice([0.98, 0.99, 1.0, 1.0, 1.01, 1.02])))
        unit_price = (product[3] * price_jitter).quantize(MONEY)
        gross = (unit_price * units).quantize(MONEY)
        discount_amount = (gross * discount_pct).quantize(MONEY, rounding=ROUND_HALF_UP)
        net = gross - discount_amount
        cogs = (
            product[4] * units * Decimal(str(rng.choice([0.98, 1.0, 1.0, 1.02])))
        ).quantize(MONEY)
        margin = net - cogs
        order_number = 100_000 + i
        posting = datetime.combine(
            sale_date, datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(hours=14, minutes=i % 47)
        updated = posting + timedelta(days=rng.choice([0, 0, 1, 2]), hours=3)
        row = {
            "transaction_id": f"TXN-{i + 1:06d}",
            "order_id": f"SO-{order_number}",
            "sale_date": sale_date,
            "posting_timestamp": posting,
            "customer_id": customer[0],
            "customer_name": customer[1],
            "customer_type": customer[2],
            "facility_state": customer[3],
            "sales_region": customer[4],
            "sales_rep_id": f"REP-{(CUSTOMERS.index(customer) * 3 + i % 7) % 42 + 1:03d}",
            "product_sku": product[0],
            "product_family": product[1],
            "procedure_category": product[2],
            "units": units,
            "unit_price": unit_price,
            "gross_sales": gross,
            "discount_pct": discount_pct,
            "discount_amount": discount_amount,
            "net_sales": net,
            "cost_of_goods": cogs,
            "gross_margin": margin,
            "currency": "USD",
            "sales_channel": rng.choices(
                ["Direct", "Distributor", "ASC Program"], weights=[72, 12, 16], k=1
            )[0],
            "contract_id": f"AGR-ORTHO-26-{310 + (CUSTOMERS.index(customer) % 5) * 7}",
            "purchase_order_number": f"CPO-{customer[0][-3:]}-{sale_date.year}-{(i % 211) + 1:04d}",
            "invoice_number": f"SI-{880000 + i}",
            "payment_status": rng.choices(
                ["PAID", "OPEN", "PARTIALLY_PAID", "DISPUTED"],
                weights=[64, 27, 6, 3],
                k=1,
            )[0],
            "source_updated_at": updated,
        }
        rows.append(row)
    return rows


def csv_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def write_lakebase_seed(rows: list[dict[str, Any]], transactional: Path) -> None:
    lakebase = transactional / "lakebase"
    shutil.rmtree(lakebase, ignore_errors=True)
    lakebase.mkdir(parents=True)
    with (lakebase / "sales_transactions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=TXN_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            {key: csv_value(row[key]) for key in TXN_FIELDS} for row in rows
        )
    columns = """
    transaction_id varchar(20) PRIMARY KEY,
    order_id varchar(20) NOT NULL,
    sale_date date NOT NULL,
    posting_timestamp timestamptz NOT NULL,
    customer_id varchar(20) NOT NULL,
    customer_name varchar(160) NOT NULL,
    customer_type varchar(50) NOT NULL,
    facility_state char(2) NOT NULL,
    sales_region varchar(40) NOT NULL,
    sales_rep_id varchar(20) NOT NULL,
    product_sku varchar(40) NOT NULL,
    product_family varchar(80) NOT NULL,
    procedure_category varchar(80) NOT NULL,
    units integer NOT NULL CHECK (units > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    gross_sales numeric(14,2) NOT NULL CHECK (gross_sales >= 0),
    discount_pct numeric(6,4) NOT NULL CHECK (discount_pct BETWEEN 0 AND 1),
    discount_amount numeric(14,2) NOT NULL CHECK (discount_amount >= 0),
    net_sales numeric(14,2) NOT NULL CHECK (net_sales >= 0),
    cost_of_goods numeric(14,2) NOT NULL CHECK (cost_of_goods >= 0),
    gross_margin numeric(14,2) NOT NULL,
    currency char(3) NOT NULL DEFAULT 'USD',
    sales_channel varchar(30) NOT NULL,
    contract_id varchar(40) NOT NULL,
    purchase_order_number varchar(40) NOT NULL,
    invoice_number varchar(40) NOT NULL UNIQUE,
    payment_status varchar(30) NOT NULL,
    source_updated_at timestamptz NOT NULL
""".strip()
    schema_sql = f"""-- Synthetic Lakebase/PostgreSQL source schema. Safe to rerun.
CREATE SCHEMA IF NOT EXISTS finance_seed;

CREATE TABLE IF NOT EXISTS finance_seed.sales_transactions (
{columns}
);

CREATE INDEX IF NOT EXISTS sales_transactions_sale_date_idx
    ON finance_seed.sales_transactions (sale_date);
CREATE INDEX IF NOT EXISTS sales_transactions_customer_idx
    ON finance_seed.sales_transactions (customer_id, sale_date);
CREATE INDEX IF NOT EXISTS sales_transactions_source_updated_idx
    ON finance_seed.sales_transactions (source_updated_at);
"""
    (lakebase / "schema.sql").write_text(schema_sql, encoding="utf-8", newline="\n")
    copy_columns = ", ".join(TXN_FIELDS)
    load_sql = f"""\\set ON_ERROR_STOP on
BEGIN;
TRUNCATE TABLE finance_seed.sales_transactions;
\\copy finance_seed.sales_transactions ({copy_columns}) FROM 'data/finance/transactional/lakebase/sales_transactions.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
COMMIT;
"""
    (lakebase / "load.sql").write_text(load_sql, encoding="utf-8", newline="\n")


def arrow_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("transaction_id", pa.string()),
            pa.field("order_id", pa.string()),
            pa.field("sale_date", pa.date32()),
            pa.field("posting_timestamp", pa.timestamp("us", tz="UTC")),
            pa.field("customer_id", pa.string()),
            pa.field("customer_name", pa.string()),
            pa.field("customer_type", pa.string()),
            pa.field("facility_state", pa.string()),
            pa.field("sales_region", pa.string()),
            pa.field("sales_rep_id", pa.string()),
            pa.field("product_sku", pa.string()),
            pa.field("product_family", pa.string()),
            pa.field("procedure_category", pa.string()),
            pa.field("units", pa.int32()),
            pa.field("unit_price", pa.decimal128(12, 2)),
            pa.field("gross_sales", pa.decimal128(14, 2)),
            pa.field("discount_pct", pa.decimal128(6, 4)),
            pa.field("discount_amount", pa.decimal128(14, 2)),
            pa.field("net_sales", pa.decimal128(14, 2)),
            pa.field("cost_of_goods", pa.decimal128(14, 2)),
            pa.field("gross_margin", pa.decimal128(14, 2)),
            pa.field("currency", pa.string()),
            pa.field("sales_channel", pa.string()),
            pa.field("contract_id", pa.string()),
            pa.field("purchase_order_number", pa.string()),
            pa.field("invoice_number", pa.string()),
            pa.field("payment_status", pa.string()),
            pa.field("source_updated_at", pa.timestamp("us", tz="UTC")),
        ]
    )


def normalize_delta(delta_path: Path) -> None:
    """Remove writer UUIDs/timestamps without changing the valid Delta snapshot."""
    log_path = delta_path / "_delta_log" / "00000000000000000000.json"
    actions = [
        json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    add_actions = [action["add"] for action in actions if "add" in action]
    old_paths = sorted(add["path"] for add in add_actions)
    replacements: dict[str, str] = {}
    for index, old_path in enumerate(old_paths):
        new_path = f"part-{index:05d}-finance-sales.c000.snappy.parquet"
        (delta_path / old_path).rename(delta_path / new_path)
        replacements[old_path] = new_path
    for action in actions:
        if "commitInfo" in action:
            action["commitInfo"]["timestamp"] = GENERATED_AT_MS
            action["commitInfo"].get("operationMetrics", {})["execution_time_ms"] = 0
        if "metaData" in action:
            action["metaData"]["id"] = "09232026-0000-4000-8000-000000000004"
            action["metaData"]["createdTime"] = GENERATED_AT_MS
        if "add" in action:
            action["add"]["path"] = replacements[action["add"]["path"]]
            action["add"]["modificationTime"] = GENERATED_AT_MS
            action["add"]["stats"] = json.dumps(
                json.loads(action["add"]["stats"]),
                separators=(",", ":"),
                sort_keys=True,
            )
    normalized = "".join(
        json.dumps(action, separators=(",", ":"), sort_keys=True) + "\n"
        for action in actions
    )
    log_path.write_text(normalized, encoding="utf-8", newline="\n")


def write_delta_seed(rows: list[dict[str, Any]], transactional: Path) -> None:
    delta_path = transactional / "delta" / "sales_transactions"
    shutil.rmtree(delta_path.parent, ignore_errors=True)
    delta_path.parent.mkdir(parents=True)
    table = pa.Table.from_pylist(rows, schema=arrow_schema())
    write_deltalake(
        delta_path,
        table,
        mode="error",
        name="finance_sales_transactions_seed",
        description="Deterministic synthetic orthopedics sales fallback seed",
        configuration={"delta.enableChangeDataFeed": "true"},
    )
    normalize_delta(delta_path)


def artifact_files(output_root: Path) -> list[Path]:
    documents = output_root / "documents"
    transactional = output_root / "transactional"
    files = list(documents.glob("*/*.pdf")) + [documents / "document_manifest.csv"]
    files += [
        path
        for path in transactional.rglob("*")
        if path.is_file() and path.name != "checksums.sha256"
    ]
    return sorted(files, key=lambda path: path.relative_to(output_root).as_posix())


def file_hashes(output_root: Path) -> dict[str, str]:
    return {
        path.relative_to(output_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in artifact_files(output_root)
    }


def write_checksums(output_root: Path) -> None:
    checksum_file = output_root / "transactional" / "checksums.sha256"
    hashes = file_hashes(output_root)
    checksum_file.write_text(
        "".join(f"{digest}  {path}\n" for path, digest in hashes.items()),
        encoding="utf-8",
        newline="\n",
    )


def generate(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    generate_pdfs(output_root)
    rows = generate_transactions()
    transactional = output_root / "transactional"
    transactional.mkdir(parents=True, exist_ok=True)
    write_lakebase_seed(rows, transactional)
    write_delta_seed(rows, transactional)
    write_checksums(output_root)


def load_csv_rows(
    path: Path, expected_fields: tuple[str, ...] | None = None
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if (
            expected_fields is not None
            and tuple(reader.fieldnames or ()) != expected_fields
        ):
            raise AssertionError(
                f"unexpected CSV schema in {path}: {reader.fieldnames}"
            )
        return list(reader)


def validate(output_root: Path) -> dict[str, Any]:
    documents = output_root / "documents"
    manifest_rows = load_csv_rows(documents / "document_manifest.csv")
    class_counts: Counter[str] = Counter()
    for row in manifest_rows:
        pdf_path = documents / row["file_path"]
        if not pdf_path.is_file():
            raise AssertionError(f"missing PDF: {pdf_path}")
        reader = PdfReader(pdf_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if len(reader.pages) != 2 or len(text) < 900:
            raise AssertionError(
                f"PDF is not a substantial two-page document: {pdf_path}"
            )
        class_counts[row["expected_class"]] += 1
    expected_counts = Counter({class_name: ROWS_PER_CLASS for class_name in CLASSES})
    if (
        class_counts != expected_counts
        or len(manifest_rows) != len(CLASSES) * ROWS_PER_CLASS
    ):
        raise AssertionError(f"unexpected PDF distribution: {class_counts}")

    csv_path = output_root / "transactional" / "lakebase" / "sales_transactions.csv"
    csv_rows = load_csv_rows(csv_path, TXN_FIELDS)
    if len(csv_rows) != ROW_COUNT:
        raise AssertionError(f"expected {ROW_COUNT} sales rows, found {len(csv_rows)}")
    if len({row["transaction_id"] for row in csv_rows}) != ROW_COUNT:
        raise AssertionError("transaction IDs are not unique")
    valid_customers = {customer[0] for customer in CUSTOMERS}
    valid_products = {product[0] for product in PRODUCTS}
    for row in csv_rows:
        gross = Decimal(row["unit_price"]) * int(row["units"])
        net = Decimal(row["gross_sales"]) - Decimal(row["discount_amount"])
        margin = Decimal(row["net_sales"]) - Decimal(row["cost_of_goods"])
        if (
            gross.quantize(MONEY) != Decimal(row["gross_sales"])
            or net != Decimal(row["net_sales"])
            or margin != Decimal(row["gross_margin"])
        ):
            raise AssertionError(
                f"incoherent financial arithmetic in {row['transaction_id']}"
            )
        if (
            row["customer_id"] not in valid_customers
            or row["product_sku"] not in valid_products
            or row["currency"] != "USD"
        ):
            raise AssertionError(
                f"invalid sales dimension reference in {row['transaction_id']}"
            )

    delta_path = output_root / "transactional" / "delta" / "sales_transactions"
    delta = DeltaTable(delta_path)
    delta_table = delta.to_pyarrow_table()
    if delta_table.num_rows != ROW_COUNT or delta.version() != 0:
        raise AssertionError("Delta seed is not a readable 3,000-row version-0 table")
    if tuple(delta_table.column_names) != TXN_FIELDS:
        raise AssertionError(f"unexpected Delta schema: {delta_table.column_names}")
    delta_total = sum(delta_table.column("net_sales").to_pylist(), Decimal("0.00"))
    csv_total = sum((Decimal(row["net_sales"]) for row in csv_rows), Decimal("0.00"))
    if delta_total != csv_total:
        raise AssertionError(
            "Delta and Lakebase seeds do not contain the same net sales"
        )

    schema_path = output_root / "transactional" / "lakebase" / "schema.sql"
    parsed = sqlglot.parse(schema_path.read_text(encoding="utf-8"), read="postgres")
    if len(parsed) != 5:
        raise AssertionError(
            f"expected five PostgreSQL DDL statements, parsed {len(parsed)}"
        )
    load_sql = (output_root / "transactional" / "lakebase" / "load.sql").read_text(
        encoding="utf-8"
    )
    copy_match = re.search(
        r"\\copy\s+finance_seed\.sales_transactions\s*\((.*?)\)\s+FROM",
        load_sql,
        re.IGNORECASE,
    )
    if copy_match is None:
        raise AssertionError(
            "Lakebase load.sql does not contain the expected psql copy command"
        )
    copy_columns = tuple(column.strip() for column in copy_match.group(1).split(","))
    if copy_columns != TXN_FIELDS:
        raise AssertionError("Lakebase copy column order does not match the seed CSV")

    expected_hashes: dict[str, str] = {}
    checksum_path = output_root / "transactional" / "checksums.sha256"
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        expected_hashes[relative] = digest
    actual_hashes = file_hashes(output_root)
    if expected_hashes != actual_hashes:
        raise AssertionError(
            "artifact checksum manifest does not match generated files"
        )
    return {
        "seed": SEED,
        "pdf_total": sum(class_counts.values()),
        "pdf_by_class": dict(sorted(class_counts.items())),
        "transaction_rows": len(csv_rows),
        "delta_version": delta.version(),
        "delta_net_sales": format(delta_total, ".2f"),
        "postgres_ddl_statements": len(parsed),
        "artifact_count": len(actual_hashes),
    }


def check_reproducible() -> dict[str, Any]:
    with (
        tempfile.TemporaryDirectory(prefix="finance-seed-a-") as first_dir,
        tempfile.TemporaryDirectory(prefix="finance-seed-b-") as second_dir,
    ):
        first = Path(first_dir) / "finance"
        second = Path(second_dir) / "finance"
        generate(first)
        generate(second)
        first_result = validate(first)
        validate(second)
        first_hashes = file_hashes(first)
        second_hashes = file_hashes(second)
        if first_hashes != second_hashes:
            differences = sorted(
                set(first_hashes) ^ set(second_hashes)
                | {
                    path
                    for path in first_hashes.keys() & second_hashes.keys()
                    if first_hashes[path] != second_hashes[path]
                }
            )
            raise AssertionError(
                f"same-seed generation is not byte-identical: {differences}"
            )
        first_result["reproducible_files_compared"] = len(first_hashes)
        first_result["byte_identical"] = True
        return first_result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/finance"),
        help="Finance output root (default: data/finance)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing outputs without regenerating",
    )
    parser.add_argument(
        "--check-reproducible",
        action="store_true",
        help="Generate twice in temporary directories and compare every byte",
    )
    args = parser.parse_args()
    if args.check_reproducible:
        result = check_reproducible()
    else:
        if not args.validate_only:
            generate(args.output)
        result = validate(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
