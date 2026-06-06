"""Unit tests for solidworks_com.urdf (no SOLIDWORKS required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from solidworks_com.urdf import Joint, Link, Robot, URDFGenerator, generate_urdf


class TestJoint:
    def _make_joint(self, joint_type: str = "revolute") -> Joint:
        return Joint(
            name="joint1",
            joint_type=joint_type,
            parent="base_link",
            child="arm_link",
            limit_lower=-1.57,
            limit_upper=1.57,
            limit_effort=10.0,
            limit_velocity=1.0,
        )

    def test_to_xml_tag(self) -> None:
        xml = self._make_joint().to_xml()
        assert xml.tag == "joint"

    def test_to_xml_name_attr(self) -> None:
        xml = self._make_joint().to_xml()
        assert xml.get("name") == "joint1"

    def test_to_xml_type_attr(self) -> None:
        xml = self._make_joint().to_xml()
        assert xml.get("type") == "revolute"

    def test_revolute_has_limit(self) -> None:
        xml = self._make_joint("revolute").to_xml()
        limit = xml.find("limit")
        assert limit is not None
        assert float(limit.get("lower")) == pytest.approx(-1.57)

    def test_prismatic_has_limit(self) -> None:
        xml = self._make_joint("prismatic").to_xml()
        assert xml.find("limit") is not None

    def test_fixed_has_no_limit(self) -> None:
        xml = self._make_joint("fixed").to_xml()
        assert xml.find("limit") is None

    def test_fixed_has_no_axis(self) -> None:
        xml = self._make_joint("fixed").to_xml()
        assert xml.find("axis") is None

    def test_revolute_has_axis(self) -> None:
        xml = self._make_joint("revolute").to_xml()
        assert xml.find("axis") is not None

    def test_parent_link_attr(self) -> None:
        xml = self._make_joint().to_xml()
        parent = xml.find("parent")
        assert parent is not None
        assert parent.get("link") == "base_link"

    def test_child_link_attr(self) -> None:
        xml = self._make_joint().to_xml()
        child = xml.find("child")
        assert child is not None
        assert child.get("link") == "arm_link"


class TestLink:
    def test_to_xml_tag(self) -> None:
        link = Link(name="base_link")
        assert link.to_xml().tag == "link"

    def test_to_xml_name_attr(self) -> None:
        link = Link(name="base_link")
        assert link.to_xml().get("name") == "base_link"

    def test_no_visual_when_mesh_absent(self) -> None:
        link = Link(name="base_link")
        assert link.to_xml().find("visual") is None

    def test_visual_present_when_mesh_given(self) -> None:
        link = Link(name="base_link", visual_mesh="meshes/base.stl")
        xml = link.to_xml()
        assert xml.find("visual") is not None

    def test_visual_mesh_filename(self) -> None:
        link = Link(name="base_link", visual_mesh="meshes/base.stl")
        xml = link.to_xml()
        mesh = xml.find(".//mesh")
        assert mesh is not None
        assert mesh.get("filename") == "meshes/base.stl"

    def test_no_inertial_when_mass_zero(self) -> None:
        link = Link(name="base_link", mass=0.0)
        assert link.to_xml().find("inertial") is None

    def test_inertial_present_when_mass_positive(self) -> None:
        link = Link(name="base_link", mass=1.5)
        xml = link.to_xml()
        assert xml.find("inertial") is not None

    def test_inertial_mass_value(self) -> None:
        link = Link(name="base_link", mass=2.0)
        xml = link.to_xml()
        mass_elem = xml.find(".//mass")
        assert mass_elem is not None
        assert float(mass_elem.get("value")) == pytest.approx(2.0)

    def test_collision_mesh_present(self) -> None:
        link = Link(name="base_link", collision_mesh="meshes/col.stl")
        xml = link.to_xml()
        assert xml.find("collision") is not None


class TestRobot:
    def _make_robot(self) -> Robot:
        robot = Robot(name="test_robot")
        robot.add_link(Link(name="base_link"))
        robot.add_link(Link(name="arm_link", visual_mesh="arm.stl"))
        robot.add_joint(Joint(
            name="joint1",
            joint_type="revolute",
            parent="base_link",
            child="arm_link",
        ))
        return robot

    def test_add_link(self) -> None:
        robot = Robot(name="r")
        robot.add_link(Link(name="l1"))
        assert len(robot.links) == 1

    def test_add_joint(self) -> None:
        robot = Robot(name="r")
        robot.add_joint(Joint("j1", "fixed", "a", "b"))
        assert len(robot.joints) == 1

    def test_to_urdf_is_xml_string(self) -> None:
        xml_str = self._make_robot().to_urdf()
        assert "<?xml" in xml_str
        assert "<robot" in xml_str

    def test_to_urdf_contains_robot_name(self) -> None:
        xml_str = self._make_robot().to_urdf()
        assert "test_robot" in xml_str

    def test_to_urdf_contains_links(self) -> None:
        xml_str = self._make_robot().to_urdf()
        assert "base_link" in xml_str
        assert "arm_link" in xml_str

    def test_to_urdf_contains_joint(self) -> None:
        xml_str = self._make_robot().to_urdf()
        assert "joint1" in xml_str

    def test_save_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "robot.urdf"
        self._make_robot().save(out)
        assert out.exists()
        assert "<?xml" in out.read_text(encoding="utf-8")


class TestURDFGenerator:
    def _make_model(self, size=None) -> MagicMock:
        model = MagicMock()
        model.title = "part"
        model.safe_size.return_value = size
        return model

    def test_generate_returns_robot(self) -> None:
        gen = URDFGenerator(self._make_model())
        robot = gen.generate("my_robot")
        assert isinstance(robot, Robot)
        assert robot.name == "my_robot"

    def test_generate_has_base_link(self) -> None:
        gen = URDFGenerator(self._make_model())
        robot = gen.generate()
        assert any(lk.name == "base_link" for lk in robot.links)

    def test_mass_estimated_from_bbox(self) -> None:
        gen = URDFGenerator(self._make_model(size=(0.1, 0.1, 0.1)))
        robot = gen.generate()
        base = next(lk for lk in robot.links if lk.name == "base_link")
        # 0.1^3 * 7850 ≈ 0.785
        assert base.mass == pytest.approx(0.001 * 7850, rel=1e-3)

    def test_mass_fallback_when_no_bbox(self) -> None:
        gen = URDFGenerator(self._make_model(size=None))
        robot = gen.generate()
        base = next(lk for lk in robot.links if lk.name == "base_link")
        assert base.mass == pytest.approx(1.0)

    def test_mesh_dir_in_filename(self) -> None:
        gen = URDFGenerator(self._make_model())
        robot = gen.generate(mesh_dir="meshes")
        base = next(lk for lk in robot.links if lk.name == "base_link")
        assert base.visual_mesh is not None
        assert base.visual_mesh.startswith("meshes/")


class TestGenerateURDF:
    def test_convenience_function(self, tmp_path: Path) -> None:
        model = MagicMock()
        model.title = "part"
        model.safe_size.return_value = None
        out = tmp_path / "robot.urdf"
        robot = generate_urdf(model, "my_robot", output_path=out)
        assert isinstance(robot, Robot)
        assert out.exists()
