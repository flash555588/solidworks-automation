"""Unit tests for URDF, manufacturing, BOM, and drawing modules."""

from __future__ import annotations

from solidworks_com.bom import BOM, BOMItem
from solidworks_com.drawing import Drawing, DrawingView, ViewType
from solidworks_com.manufacturing import (
    CheckResult,
    CheckSeverity,
    ManufacturingProcess,
    ManufacturingReport,
)
from solidworks_com.urdf import Joint, Link, Robot


class TestURDF:
    def test_link_creation(self) -> None:
        link = Link(name="base_link", mass=1.0)
        assert link.name == "base_link"
        assert link.mass == 1.0

    def test_link_to_xml(self) -> None:
        link = Link(name="base_link", mass=1.0, visual_mesh="model.stl")
        xml = link.to_xml()
        assert xml.get("name") == "base_link"

    def test_joint_creation(self) -> None:
        joint = Joint(
            name="joint1",
            joint_type="revolute",
            parent="base",
            child="link1",
        )
        assert joint.name == "joint1"
        assert joint.joint_type == "revolute"

    def test_joint_to_xml(self) -> None:
        joint = Joint(
            name="joint1",
            joint_type="revolute",
            parent="base",
            child="link1",
            limit_lower=-1.57,
            limit_upper=1.57,
        )
        xml = joint.to_xml()
        assert xml.get("name") == "joint1"
        assert xml.get("type") == "revolute"

    def test_robot_creation(self) -> None:
        robot = Robot(name="test_robot")
        assert robot.name == "test_robot"
        assert len(robot.links) == 0

    def test_robot_add_link(self) -> None:
        robot = Robot(name="test_robot")
        robot.add_link(Link(name="base"))
        assert len(robot.links) == 1

    def test_robot_to_urdf(self) -> None:
        robot = Robot(name="test_robot")
        robot.add_link(Link(name="base"))
        robot.add_link(Link(name="link1"))
        robot.add_joint(Joint(
            name="joint1",
            joint_type="fixed",
            parent="base",
            child="link1",
        ))
        urdf = robot.to_urdf()
        assert "test_robot" in urdf
        assert "base" in urdf
        assert "link1" in urdf


class TestManufacturing:
    def test_check_result(self) -> None:
        r = CheckResult(
            check_name="size",
            passed=True,
            severity=CheckSeverity.INFO,
            message="OK",
        )
        assert r.passed is True

    def test_check_result_to_dict(self) -> None:
        r = CheckResult(
            check_name="size",
            passed=False,
            severity=CheckSeverity.ERROR,
            message="Too large",
            value=1.5,
            limit=1.0,
        )
        d = r.to_dict()
        assert d["check"] == "size"
        assert d["passed"] is False

    def test_report_creation(self) -> None:
        r = ManufacturingReport(
            model_name="test",
            process=ManufacturingProcess.CNC_MILLING,
        )
        assert r.model_name == "test"
        assert r.success is True

    def test_report_add_result(self) -> None:
        r = ManufacturingReport()
        r.add_result(CheckResult(
            check_name="test",
            passed=True,
            severity=CheckSeverity.INFO,
            message="OK",
        ))
        assert r.total_checks == 1
        assert r.passed_checks == 1

    def test_report_summary(self) -> None:
        r = ManufacturingReport(model_name="test")
        r.add_result(CheckResult(
            check_name="test",
            passed=True,
            severity=CheckSeverity.INFO,
            message="OK",
        ))
        s = r.summary()
        assert "test" in s


class TestBOM:
    def test_bom_item(self) -> None:
        item = BOMItem(
            item_number=1,
            part_number="P001",
            description="Screw",
            quantity=10,
            unit_cost=0.50,
        )
        assert item.total_cost == 5.0

    def test_bom_creation(self) -> None:
        bom = BOM(project_name="Test Project")
        assert bom.project_name == "Test Project"
        assert bom.total_items == 0

    def test_bom_add_item(self) -> None:
        bom = BOM()
        bom.add_item(BOMItem(
            item_number=1,
            part_number="P001",
            description="Part 1",
            quantity=5,
        ))
        assert bom.total_items == 1
        assert bom.total_quantity == 5

    def test_bom_to_csv(self) -> None:
        bom = BOM(project_name="Test")
        bom.add_item(BOMItem(
            item_number=1,
            part_number="P001",
            description="Screw",
            quantity=10,
            unit_cost=0.50,
        ))
        csv = bom.to_csv()
        assert "P001" in csv
        assert "Screw" in csv

    def test_bom_to_dict(self) -> None:
        bom = BOM(project_name="Test")
        d = bom.to_dict()
        assert d["project"] == "Test"
        assert "summary" in d


class TestDrawing:
    def test_view_creation(self) -> None:
        view = DrawingView(view_type=ViewType.FRONT)
        assert view.view_type == ViewType.FRONT
        assert view.scale == 1.0

    def test_drawing_creation(self) -> None:
        drawing = Drawing(title="Test Drawing")
        assert drawing.title == "Test Drawing"
        assert len(drawing.views) == 0

    def test_drawing_add_view(self) -> None:
        drawing = Drawing()
        drawing.add_view(DrawingView(view_type=ViewType.FRONT))
        assert len(drawing.views) == 1

    def test_drawing_to_dict(self) -> None:
        drawing = Drawing(title="Test")
        drawing.add_view(DrawingView(view_type=ViewType.FRONT))
        d = drawing.to_dict()
        assert d["title"] == "Test"
        assert len(d["views"]) == 1

    def test_drawing_generate_html(self) -> None:
        drawing = Drawing(title="Test")
        drawing.add_view(DrawingView(view_type=ViewType.FRONT))
        html = drawing.generate_html()
        assert "Test" in html
        assert "FRONT" in html
