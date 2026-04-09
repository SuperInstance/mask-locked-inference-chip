#!/usr/bin/env python3
"""Semiconductor manufacturing flow simulator.

Simulates the full mask-locked chip manufacturing pipeline:
wafer fab, wafer probe, die sort, packaging, final test.
"""
import random, math
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class FabPhase(Enum):
    WAFER_START = "wafer_start"
    PHOTOLITH = "photolith"
    ETCH = "etch"
    DEPOSITION = "deposition"
    CMP = "cmp"
    WAFER_PROBE = "wafer_probe"
    DIE_SORT = "die_sort"
    PACKAGING = "packaging"
    FINAL_TEST = "final_test"
    SHIP = "ship"


class DieStatus(Enum):
    GOOD = "good"
    DEFECTIVE = "defective"
    PARTIAL = "partial"


@dataclass
class Die:
    x: int
    y: int
    status: DieStatus = DieStatus.GOOD
    defect_density: float = 0.0
    bin_grade: str = "GOLD"
    test_results: Dict = field(default_factory=dict)
    pkg_id: Optional[str] = None


@dataclass
class Wafer:
    wafer_id: int
    diameter_mm: float = 300  # 300mm standard
    die_size_mm: float = 5.0  # 5mm x 5mm die
    dies: List[Die] = field(default_factory=list)
    street_um: float = 100  # dicing street width
    edge_exclusion_mm: float = 3.0

    def __post_init__(self):
        self._generate_dies()

    def _generate_dies(self):
        usable = self.diameter_mm / 2 - self.edge_exclusion_mm
        pitch = self.die_size_mm + self.street_um / 1000
        n = int(usable / pitch)
        for y in range(-n, n + 1):
            for x in range(-n, n + 1):
                # Circular mask for wafer
                cx = x * pitch + pitch / 2
                cy = y * pitch + pitch / 2
                if math.sqrt(cx * cx + cy * cy) > usable:
                    continue
                self.dies.append(Die(x, y))

    @property
    def gross_die(self) -> int:
        return len(self.dies)

    @property
    def good_die(self) -> int:
        return sum(1 for d in self.dies if d.status == DieStatus.GOOD)

    @property
    def yield_pct(self) -> float:
        return self.good_die / self.gross_die * 100 if self.gross_die > 0 else 0


class WaferFab:
    """Simulate wafer fabrication with defect model."""

    def __init__(self, defect_density: float = 0.1,  # defects/cm2
                 process_nm: int = 28):
        self.defect_density = defect_density
        self.process_nm = process_nm
        self.wafers: List[Wafer] = []
        self.lot_id: Optional[str] = None

    def start_lot(self, lot_id: str, wafer_count: int = 25,
                  die_size_mm: float = 5.0) -> str:
        self.lot_id = lot_id
        self.wafers = []
        for i in range(wafer_count):
            w = Wafer(wafer_id=i, die_size_mm=die_size_mm)
            self._simulate_fab(w)
            self.wafers.append(w)
        return lot_id

    def _simulate_fab(self, wafer: Wafer):
        """Simulate fab with Poisson defect model."""
        die_area_cm2 = (wafer.die_size_mm / 10) ** 2
        for die in wafer.dies:
            # Poisson probability of zero defects
            lambda_val = self.defect_density * die_area_cm2
            p_zero = math.exp(-lambda_val)
            # Core vs edge: better yield at center
            dist = math.sqrt(die.x ** 2 + die.y ** 2)
            max_dist = max(math.sqrt(d.x ** 2 + d.y ** 2) for d in wafer.dies) or 1
            edge_factor = 1.0 + (dist / max_dist) * 0.3
            effective_lambda = lambda_val * edge_factor

            if random.random() > math.exp(-effective_lambda):
                die.status = DieStatus.DEFECTIVE
                die.defect_density = effective_lambda
            else:
                die.status = DieStatus.GOOD
                # Bin grading
                r = random.random()
                if r < 0.85:
                    die.bin_grade = "GOLD"
                elif r < 0.95:
                    die.bin_grade = "SILVER"
                else:
                    die.bin_grade = "BRONZE"


class PackagingLine:
    """Simulate packaging and final test."""

    PACKAGE_TYPES = {
        "QFN": {"pins": 48, "cost": 0.15, "lead_time_days": 3},
        "BGA": {"pins": 256, "cost": 0.45, "lead_time_days": 5},
        "WLCSP": {"pins": 0, "cost": 0.08, "lead_time_days": 2},
    }

    def __init__(self, pkg_type: str = "QFN"):
        self.pkg_type = pkg_type
        self.info = self.PACKAGE_TYPES.get(pkg_type, self.PACKAGE_TYPES["QFN"])

    def package_wafer(self, wafer: Wafer) -> Dict:
        """Package good dies from wafer."""
        good = [d for d in wafer.dies if d.status == DieStatus.GOOD]
        packaged = []
        for i, die in enumerate(good):
            # 2% packaging yield loss
            if random.random() < 0.02:
                die.status = DieStatus.DEFECTIVE
                continue
            die.pkg_id = f"{wafer.wafer_id:03d}-{die.x:03d}-{die.y:03d}"
            # Final test
            die.test_results["final"] = self._final_test(die)
            packaged.append(die)

        by_grade = {}
        for d in packaged:
            by_grade.setdefault(d.bin_grade, []).append(d)

        return {"wafer": wafer.wafer_id, "packaged": len(packaged),
                "lost": len(good) - len(packaged),
                "by_grade": {k: len(v) for k, v in by_grade.items()},
                "pkg_cost": self.info["cost"] * len(packaged)}

    def _final_test(self, die: Die) -> Dict:
        """Final test: electrical, thermal, functional."""
        return {
            "electrical": random.random() < 0.99,
            "thermal": random.random() < 0.995,
            "functional": random.random() < 0.998,
            "leakage_ma": round(random.uniform(0.5, 2.0), 2),
            "max_freq_mhz": random.randint(450, 550),
        }


class ManufacturingReport:
    """Generate manufacturing reports."""

    @staticmethod
    def lot_report(fab: WaferFab, pkg_line: PackagingLine) -> Dict:
        total_gross = sum(w.gross_die for w in fab.wafers)
        total_good = sum(w.good_die for w in fab.wafers)
        total_yield = total_good / total_gross * 100 if total_gross > 0 else 0

        # Package all wafers
        all_packaged = []
        by_grade = {"GOLD": 0, "SILVER": 0, "BRONZE": 0}
        total_pkg_cost = 0
        for w in fab.wafers:
            result = pkg_line.package_wafer(w)
            all_packaged.append(result)
            for grade, count in result["by_grade"].items():
                by_grade[grade] += count
            total_pkg_cost += result["pkg_cost"]

        total_shipped = sum(r["packaged"] for r in all_packaged)

        # Revenue estimate
        prices = {"GOLD": 25.0, "SILVER": 15.0, "BRONZE": 8.0}
        revenue = sum(by_grade[g] * prices[g] for g in by_grade)

        return {
            "lot_id": fab.lot_id,
            "wafers": len(fab.wafers),
            "process_nm": fab.process_nm,
            "total_gross_die": total_gross,
            "total_good_die": total_good,
            "wafer_yield_pct": round(total_yield, 1),
            "packaged": total_shipped,
            "by_grade": by_grade,
            "package_cost": round(total_pkg_cost, 2),
            "revenue": round(revenue, 2),
            "margin": round(revenue - total_pkg_cost, 2),
            "per_wafer": {
                "avg_gross": round(total_gross / len(fab.wafers)),
                "avg_good": round(total_good / len(fab.wafers)),
                "avg_yield": round(total_yield, 1),
            },
        }


def demo():
    print("=== Semiconductor Manufacturing Flow ===\n")

    # Create fab
    fab = WaferFab(defect_density=0.1, process_nm=28)
    print(f"Process: {fab.process_nm}nm, Defect density: {fab.defect_density} defects/cm2")
    print()

    # Start lot
    fab.start_lot("LOT-2024-001", wafer_count=1, die_size_mm=20.0)
    print(f"Lot: {fab.lot_id}, Wafers: {len(fab.wafers)}")

    for w in fab.wafers[:3]:
        print(f"  Wafer {w.wafer_id}: {w.gross_die} gross, {w.good_die} good ({w.yield_pct:.1f}%)")
    print(f"  ... ({len(fab.wafers)} total wafers)")
    print()

    # Packaging
    pkg = PackagingLine("QFN")
    print(f"Package: {pkg.pkg_type}, Cost: ${pkg.info['cost']}/unit, Lead time: {pkg.info['lead_time_days']}d")
    print()

    # Wafer-level results
    print("--- Wafer-Level Yield ---")
    yields = [w.yield_pct for w in fab.wafers]
    print(f"  Avg yield: {sum(yields)/len(yields):.1f}%")
    print(f"  Best wafer: {max(yields):.1f}%")
    print(f"  Worst wafer: {min(yields):.1f}%")
    print()

    # Package first wafer
    print("--- Packaging (Wafer 0) ---")
    result = pkg.package_wafer(fab.wafers[0])
    print(f"  Packaged: {result['packaged']}, Lost: {result['lost']}")
    for grade, count in result["by_grade"].items():
        print(f"    {grade}: {count}")
    print(f"  Pkg cost: ${result['pkg_cost']:.2f}")
    print()

    # Full lot report
    print("--- Lot Report ---")
    report = ManufacturingReport.lot_report(fab, pkg)
    print(f"  Wafers: {report['wafers']}")
    print(f"  Gross die: {report['total_gross_die']}")
    print(f"  Good die: {report['total_good_die']}")
    print(f"  Wafer yield: {report['wafer_yield_pct']}%")
    print(f"  Packaged: {report['packaged']}")
    for grade, count in report["by_grade"].items():
        print(f"    {grade}: {count}")
    print(f"  Package cost: ${report['package_cost']:.2f}")
    print(f"  Revenue: ${report['revenue']:.2f}")
    print(f"  Margin: ${report['margin']:.2f}")
    print()

    # Sensitivity analysis
    print("--- Yield Sensitivity ---")
    for dd in [0.05, 0.1, 0.2, 0.5]:
        f = WaferFab(defect_density=dd, process_nm=28)
        f.start_lot("TEST", 1, 5.0)
        y = f.wafers[0].yield_pct
        print(f"  {dd:.2f} def/cm2: {y:.1f}% yield")


if __name__ == "__main__":
    demo()
