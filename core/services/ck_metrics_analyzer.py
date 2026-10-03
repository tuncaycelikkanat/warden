"""Chidamber & Kemerer (CK) Object-Oriented Metrics Suite for WARDEN (Section F1/F2).

Computes classic and modern object-oriented complexity metrics via Python AST & networkx:
1. WMC (Weighted Methods per Class) — Cyclomatic complexity sum of all class methods.
2. DIT (Depth of Inheritance Tree) — Maximum inheritance depth in project hierarchy.
3. NOC (Number of Children) — Number of immediate subclasses in project hierarchy.
4. CBO (Coupling Between Object Classes) — Number of coupled classes via calls, annotations, bases.
5. RFC (Response For a Class) — Total response set of callable internal and external methods.
6. Hybrid LCOM — LCOM4 (connected component partition count) & Henderson-Sellers LCOM* (0.0-1.0).
7. Architectural Smell & Anti-Pattern Detection — God Class, Brain Class, High Coupling, Fragile Hierarchy, Data Class.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class ClassCKMetrics:
    """CK metrics and architectural smell profile for an individual Python class."""

    class_name: str
    file_path: str
    line_number: int
    wmc: int  # Weighted Methods per Class
    dit: int  # Depth of Inheritance Tree
    noc: int  # Number of Children
    cbo: int  # Coupling Between Object classes
    rfc: int  # Response For a Class
    lcom4: int  # Lack of Cohesion in Methods (LCOM4 components)
    lcom_star: float  # Henderson-Sellers normalized cohesion loss (0.0 - 1.0)
    methods_count: int
    fields_count: int
    detected_smells: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CKMetricsReport:
    """Aggregated CK metrics report across an entire repository or package."""

    target_path: str
    total_classes_analyzed: int
    avg_wmc: float
    max_wmc: int
    avg_dit: float
    max_dit: int
    avg_cbo: float
    max_cbo: int
    avg_lcom4: float
    smells_summary: dict[str, int] = field(default_factory=dict)
    classes: list[ClassCKMetrics] = field(default_factory=list)
    high_risk_classes: list[ClassCKMetrics] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classes"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.classes]
        data["high_risk_classes"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.high_risk_classes]
        return data


class CKMetricsAnalyzer:
    """Analyzes Python class ASTs to compute Chidamber & Kemerer object-oriented metrics."""

    def __init__(self) -> None:
        pass

    def _compute_method_cyclomatic_complexity(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> int:
        """Calculates McCabe Cyclomatic Complexity for a single method."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.While,
                    ast.For,
                    ast.AsyncFor,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                    ast.comprehension,
                    ast.IfExp,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += max(1, len(child.values) - 1)
        return complexity

    def _extract_accessed_attributes(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> set[str]:
        """Finds all instance attributes accessed on 'self' (e.g. self.db, self.client)."""
        attrs: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "self":
                attrs.add(child.attr)
        return attrs

    def _extract_called_methods(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> tuple[set[str], set[str]]:
        """Extracts internal method calls (self.method()) and external method calls (obj.method())."""
        internal_calls: set[str] = set()
        external_calls: set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if isinstance(child.func.value, ast.Name) and child.func.value.id == "self":
                    internal_calls.add(child.func.attr)
                else:
                    external_calls.add(child.func.attr)
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                external_calls.add(child.func.id)

        return internal_calls, external_calls

    def _extract_coupled_classes(
        self,
        class_node: ast.ClassDef,
        known_classes: set[str] | None = None,
    ) -> set[str]:
        """Identifies other distinct object classes coupled to this class."""
        coupled: set[str] = set()
        builtin_ignores = {
            "object",
            "Exception",
            "BaseException",
            "ValueError",
            "TypeError",
            "KeyError",
            "dict",
            "list",
            "set",
            "tuple",
            "str",
            "int",
            "float",
            "bool",
            "Any",
            "Optional",
            "Union",
            "Callable",
            "BaseModel",
            "SQLModel",
        }

        # 1. Base classes
        for base in class_node.bases:
            name = ast.unparse(base).split(".")[-1]
            if name and name not in builtin_ignores and name != class_node.name:
                coupled.add(name)

        # 2. Type annotations and instantiations in body
        for child in ast.walk(class_node):
            if isinstance(child, ast.Name):
                # Standard PascalCase naming heuristic for class types
                if (
                    child.id[0].isupper()
                    and child.id not in builtin_ignores
                    and child.id != class_node.name
                    and not child.id.isupper()  # ignore CONSTANTS
                ):
                    if known_classes is None or child.id in known_classes:
                        coupled.add(child.id)

        return coupled

    def _compute_lcom(
        self,
        method_attrs: dict[str, set[str]],
        internal_calls: dict[str, set[str]],
    ) -> tuple[int, float]:
        """Computes LCOM4 (connected components) and Henderson-Sellers LCOM* (normalized 0.0 - 1.0).

        Excludes dunder methods (e.g. __init__, __repr__) as constructors access multiple fields
        to initialize them, which would otherwise artificially bridge independent methods.
        """
        filtered_attrs = {
            m: attrs for m, attrs in method_attrs.items()
            if not (m.startswith("__") and m.endswith("__"))
        }
        filtered_calls = {
            m: calls for m, calls in internal_calls.items()
            if not (m.startswith("__") and m.endswith("__"))
        }

        methods = list(filtered_attrs.keys())
        m_count = len(methods)

        if m_count <= 1:
            return 1, 0.0

        # Build method cohesion graph
        G = nx.Graph()
        for m in methods:
            G.add_node(m)

        all_attributes: set[str] = set()
        for attrs in filtered_attrs.values():
            all_attributes.update(attrs)

        # Add edges between methods sharing attributes or calling each other
        for i in range(m_count):
            m1 = methods[i]
            for j in range(i + 1, m_count):
                m2 = methods[j]
                shared_attrs = filtered_attrs[m1] & filtered_attrs[m2]
                is_calling = (m2 in filtered_calls.get(m1, set())) or (m1 in filtered_calls.get(m2, set()))

                if shared_attrs or is_calling:
                    G.add_edge(m1, m2)

        # LCOM4 = number of connected components
        lcom4 = max(1, nx.number_connected_components(G))

        # Henderson-Sellers LCOM*
        a_count = len(all_attributes)
        if a_count == 0 or m_count <= 1:
            lcom_star = 0.0
        else:
            sum_mu = sum(sum(1 for m in methods if attr in filtered_attrs[m]) for attr in all_attributes)
            raw_hs = (m_count - (sum_mu / a_count)) / (m_count - 1)
            lcom_star = max(0.0, min(1.0, round(raw_hs, 2)))

        return lcom4, lcom_star

    def _detect_architectural_smells(
        self,
        wmc: int,
        dit: int,
        noc: int,
        cbo: int,
        rfc: int,
        lcom4: int,
        lcom_star: float,
        methods_count: int,
        fields_count: int,
    ) -> tuple[list[str], list[str]]:
        """Identifies architectural anti-patterns and generates actionable refactoring recommendations."""
        smells: list[str] = []
        recommendations: list[str] = []

        # 1. God Class / Blob
        if (wmc >= 40 and cbo >= 10 and lcom4 >= 2) or (wmc >= 60):
            smells.append("God Class")
            recommendations.append(
                "Bu sınıf aşırı fazla sorumluluk üstleniyor (WMC >= 40, LCOM4 >= 2). Tek Sorumluluk Prensibi (SRP) gereğince alt servislere bölünmelidir."
            )

        # 2. Brain Class (Complex methods concentration)
        if wmc >= 30 and methods_count >= 12 and "God Class" not in smells:
            smells.append("Brain Class")
            recommendations.append(
                "Sınıf içinde aşırı dallanmış karmaşık metotlar yoğunlaşmış (WMC >= 30). Metot düzeyinde Extract Method refactoring uygulanmalıdır."
            )

        # 3. High Coupling (Tight coupling)
        if cbo >= 14 or rfc >= 50:
            smells.append("High Coupling")
            recommendations.append(
                f"Sınıf dış sistem ve sınıflara aşırı bağımlı (CBO={cbo}, RFC={rfc}). Dependency Inversion veya Arayüz (Protocol) ayrımı uygulanmalıdır."
            )

        # 4. Fragile Base Class / Deep Hierarchy
        if dit >= 4:
            smells.append("Fragile Hierarchy")
            recommendations.append(
                f"Kalıtım derinliği çok yüksek (DIT={dit}). 'Composition over Inheritance' prensibi ile kalıtım yerine kompozisyon tercih edilmelidir."
            )

        # 5. Data Class (Anemic Domain Model)
        if fields_count >= 5 and methods_count <= 2 and wmc <= 4:
            smells.append("Data Class")
            recommendations.append(
                "Sınıf yalnızca veri taşıyıcı gibi davranıyor. Davranışlar veriyle birleştirilmeli veya Pydantic/dataclass ile modellenmelidir."
            )

        # 6. Swiss Army Knife
        if methods_count >= 20 and lcom4 >= 3 and "God Class" not in smells:
            smells.append("Swiss Army Knife")
            recommendations.append(
                f"Sınıf birbirinden bağımsız çok sayıda araç metodu barındırıyor (LCOM4={lcom4}). Modüler servis sınıflarına parçalanmalıdır."
            )

        return smells, recommendations

    def analyze(self, target_path: Path | str = "core") -> CKMetricsReport:
        """Parses all Python classes in the target path and computes full CK metrics suite."""
        p = Path(target_path).resolve()
        py_files: list[Path] = []

        if p.is_file() and p.suffix == ".py":
            py_files = [p]
        elif p.is_dir():
            py_files = [f for f in p.rglob("*.py") if ".venv" not in f.parts and "tests" not in f.parts]

        # Phase 1: Collect class definitions, ASTs, and inheritance hierarchy
        class_nodes: dict[str, tuple[ast.ClassDef, Path]] = {}
        all_class_names: set[str] = set()
        inheritance_graph = nx.DiGraph()

        for f in py_files:
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except Exception as err:
                logger.debug(f"Could not parse {f} for CK metrics: {err}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_nodes[node.name] = (node, f)
                    all_class_names.add(node.name)
                    inheritance_graph.add_node(node.name)

        # Build inheritance edges: base -> derived
        for name, (c_node, _) in class_nodes.items():
            for base in c_node.bases:
                base_name = ast.unparse(base).split(".")[-1]
                if base_name in all_class_names:
                    inheritance_graph.add_edge(base_name, name)

        # Phase 2: Compute CK metrics per class
        class_metrics_list: list[ClassCKMetrics] = []

        for name, (c_node, file_path) in class_nodes.items():
            method_attrs: dict[str, set[str]] = {}
            internal_calls: dict[str, set[str]] = {}
            all_external_calls: set[str] = set()
            wmc = 0
            methods_count = 0
            all_fields: set[str] = set()

            for item in c_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods_count += 1
                    method_wmc = self._compute_method_cyclomatic_complexity(item)
                    wmc += method_wmc

                    attrs = self._extract_accessed_attributes(item)
                    method_attrs[item.name] = attrs
                    all_fields.update(attrs)

                    i_calls, e_calls = self._extract_called_methods(item)
                    internal_calls[item.name] = i_calls
                    all_external_calls.update(e_calls)

            # DIT (Depth of Inheritance Tree)
            dit = 1
            ancestors = nx.ancestors(inheritance_graph, name)
            if ancestors:
                # Find longest path from any root ancestor
                max_path = 0
                for anc in ancestors:
                    if inheritance_graph.in_degree(anc) == 0:
                        try:
                            paths = list(nx.all_simple_paths(inheritance_graph, anc, name))
                            if paths:
                                max_path = max(max_path, max(len(path) - 1 for path in paths))
                        except Exception as exc:
                            logger.debug("Failed computing path from %s to %s: %s", anc, name, exc)
                dit = max(1, max_path + 1)

            # NOC (Number of Children)
            noc = inheritance_graph.out_degree(name)

            # CBO (Coupling Between Object Classes)
            coupled_classes = self._extract_coupled_classes(c_node, known_classes=all_class_names)
            cbo = len(coupled_classes)

            # RFC (Response For a Class)
            rfc = methods_count + len(all_external_calls)

            # LCOM4 and Henderson-Sellers LCOM*
            lcom4, lcom_star = self._compute_lcom(method_attrs, internal_calls)

            # Architectural Smells
            smells, recs = self._detect_architectural_smells(
                wmc=wmc,
                dit=dit,
                noc=noc,
                cbo=cbo,
                rfc=rfc,
                lcom4=lcom4,
                lcom_star=lcom_star,
                methods_count=methods_count,
                fields_count=len(all_fields),
            )

            class_metrics_list.append(
                ClassCKMetrics(
                    class_name=name,
                    file_path=str(file_path),
                    line_number=c_node.lineno,
                    wmc=wmc,
                    dit=dit,
                    noc=noc,
                    cbo=cbo,
                    rfc=rfc,
                    lcom4=lcom4,
                    lcom_star=lcom_star,
                    methods_count=methods_count,
                    fields_count=len(all_fields),
                    detected_smells=smells,
                    recommendations=recs,
                )
            )

        # Sort classes by WMC descending
        class_metrics_list.sort(key=lambda c: c.wmc, reverse=True)

        n = len(class_metrics_list)
        avg_wmc = round(sum(c.wmc for c in class_metrics_list) / max(1, n), 1)
        max_wmc = max((c.wmc for c in class_metrics_list), default=0)
        avg_dit = round(sum(c.dit for c in class_metrics_list) / max(1, n), 1)
        max_dit = max((c.dit for c in class_metrics_list), default=1)
        avg_cbo = round(sum(c.cbo for c in class_metrics_list) / max(1, n), 1)
        max_cbo = max((c.cbo for c in class_metrics_list), default=0)
        avg_lcom4 = round(sum(c.lcom4 for c in class_metrics_list) / max(1, n), 1)

        smells_summary: dict[str, int] = {}
        for c in class_metrics_list:
            for s in c.detected_smells:
                smells_summary[s] = smells_summary.get(s, 0) + 1

        high_risk = [c for c in class_metrics_list if c.detected_smells or c.wmc >= 30 or c.lcom4 >= 3]

        summary = (
            f"Toplam {n} Python sınıfı analiz edildi. Ortalama WMC: {avg_wmc} (Max: {max_wmc}), "
            f"Ortalama CBO: {avg_cbo} (Max: {max_cbo}), Ortalama LCOM4: {avg_lcom4}. "
            f"{len(high_risk)} adet yüksek karmaşıklıklı veya mimari kokulu sınıf tespit edildi."
        )

        return CKMetricsReport(
            target_path=str(p),
            total_classes_analyzed=n,
            avg_wmc=avg_wmc,
            max_wmc=max_wmc,
            avg_dit=avg_dit,
            max_dit=max_dit,
            avg_cbo=avg_cbo,
            max_cbo=max_cbo,
            avg_lcom4=avg_lcom4,
            smells_summary=smells_summary,
            classes=class_metrics_list,
            high_risk_classes=high_risk,
            summary=summary,
        )
