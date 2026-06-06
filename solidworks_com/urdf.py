"""URDF (Unified Robot Description Format) generator.

Generates robot description files from CAD models for:
- ROS/ROS2 robotics framework
- Gazebo simulation
- MoveIt motion planning
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)


@dataclass
class Joint:
    """Robot joint definition."""

    name: str
    joint_type: str  # "revolute", "prismatic", "fixed", "continuous"
    parent: str
    child: str
    origin_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    origin_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    limit_lower: float = 0.0
    limit_upper: float = 0.0
    limit_effort: float = 0.0
    limit_velocity: float = 0.0

    def to_xml(self) -> Element:
        """Convert to URDF XML element."""
        joint = Element("joint")
        joint.set("name", self.name)
        joint.set("type", self.joint_type)

        # Origin
        origin = SubElement(joint, "origin")
        origin.set("xyz", f"{self.origin_xyz[0]:.6f} {self.origin_xyz[1]:.6f} {self.origin_xyz[2]:.6f}")
        origin.set("rpy", f"{self.origin_rpy[0]:.6f} {self.origin_rpy[1]:.6f} {self.origin_rpy[2]:.6f}")

        # Parent
        parent = SubElement(joint, "parent")
        parent.set("link", self.parent)

        # Child
        child = SubElement(joint, "child")
        child.set("link", self.child)

        # Axis
        if self.joint_type not in ("fixed",):
            axis = SubElement(joint, "axis")
            axis.set("xyz", f"{self.axis[0]:.6f} {self.axis[1]:.6f} {self.axis[2]:.6f}")

        # Limit
        if self.joint_type in ("revolute", "prismatic"):
            limit = SubElement(joint, "limit")
            limit.set("lower", f"{self.limit_lower:.6f}")
            limit.set("upper", f"{self.limit_upper:.6f}")
            limit.set("effort", f"{self.limit_effort:.6f}")
            limit.set("velocity", f"{self.limit_velocity:.6f}")

        return joint


@dataclass
class Link:
    """Robot link definition."""

    name: str
    visual_mesh: str | None = None
    visual_origin_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    visual_origin_rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)
    collision_mesh: str | None = None
    mass: float = 0.0
    inertia_ixx: float = 0.0
    inertia_iyy: float = 0.0
    inertia_izz: float = 0.0

    def to_xml(self) -> Element:
        """Convert to URDF XML element."""
        link = Element("link")
        link.set("name", self.name)

        # Visual
        if self.visual_mesh:
            visual = SubElement(link, "visual")
            origin = SubElement(visual, "origin")
            origin.set("xyz", f"{self.visual_origin_xyz[0]:.6f} {self.visual_origin_xyz[1]:.6f} {self.visual_origin_xyz[2]:.6f}")
            origin.set("rpy", f"{self.visual_origin_rpy[0]:.6f} {self.visual_origin_rpy[1]:.6f} {self.visual_origin_rpy[2]:.6f}")
            geometry = SubElement(visual, "geometry")
            mesh = SubElement(geometry, "mesh")
            mesh.set("filename", self.visual_mesh)

        # Collision
        if self.collision_mesh:
            collision = SubElement(link, "collision")
            origin = SubElement(collision, "origin")
            origin.set("xyz", "0 0 0")
            origin.set("rpy", "0 0 0")
            geometry = SubElement(collision, "geometry")
            mesh = SubElement(geometry, "mesh")
            mesh.set("filename", self.collision_mesh)

        # Inertial
        if self.mass > 0:
            inertial = SubElement(link, "inertial")
            origin = SubElement(inertial, "origin")
            origin.set("xyz", "0 0 0")
            origin.set("rpy", "0 0 0")
            mass_elem = SubElement(inertial, "mass")
            mass_elem.set("value", f"{self.mass:.6f}")
            inertia = SubElement(inertial, "inertia")
            inertia.set("ixx", f"{self.inertia_ixx:.6e}")
            inertia.set("iyy", f"{self.inertia_iyy:.6e}")
            inertia.set("izz", f"{self.inertia_izz:.6e}")

        return link


@dataclass
class Robot:
    """Robot description."""

    name: str
    links: list[Link] = field(default_factory=list)
    joints: list[Joint] = field(default_factory=list)

    def add_link(self, link: Link) -> None:
        """Add a link to the robot."""
        self.links.append(link)

    def add_joint(self, joint: Joint) -> None:
        """Add a joint to the robot."""
        self.joints.append(joint)

    def to_urdf(self) -> str:
        """Generate URDF XML string."""
        robot = Element("robot")
        robot.set("name", self.name)

        # Add links
        for link in self.links:
            robot.append(link.to_xml())

        # Add joints
        for joint in self.joints:
            robot.append(joint.to_xml())

        # Pretty print
        rough_string = tostring(robot, encoding="unicode")
        reparsed = parseString(rough_string)
        return reparsed.toprettyxml(indent="  ")

    def save(self, path: str | Path) -> None:
        """Save URDF to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_urdf(), encoding="utf-8")
        logger.info("Saved URDF to %s", path)


class URDFGenerator:
    """Generates URDF from SOLIDWORKS model."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def generate(
        self,
        robot_name: str = "robot",
        *,
        mesh_dir: str | None = None,
    ) -> Robot:
        """Generate URDF from current model.

        Args:
            robot_name: Name of the robot.
            mesh_dir: Directory for mesh files (relative to URDF).

        Returns:
            Robot object with links and joints.
        """
        robot = Robot(name=robot_name)

        # Get model info
        title = self.model.title
        bbox = self._get_bounding_box()

        # Create base link
        base_link = Link(
            name="base_link",
            visual_mesh=f"{mesh_dir}/{title}.stl" if mesh_dir else f"{title}.stl",
            mass=self._estimate_mass(bbox),
        )
        robot.add_link(base_link)

        return robot

    def _get_bounding_box(self) -> tuple[float, float, float] | None:
        return self.model.safe_size()

    def _estimate_mass(self, size: tuple[float, float, float] | None) -> float:
        """Estimate mass from bounding box (assuming steel)."""
        if size is None:
            return 1.0
        volume = size[0] * size[1] * size[2]
        density = 7850  # kg/m³ (steel)
        return volume * density


def generate_urdf(
    model: Any,
    robot_name: str = "robot",
    *,
    output_path: str | Path | None = None,
    mesh_dir: str | None = None,
) -> Robot:
    """Convenience function to generate URDF.

    Example::

        from solidworks_com import generate_urdf

        # Generate URDF
        robot = generate_urdf(
            part,
            robot_name="my_robot",
            output_path="robot.urdf",
            mesh_dir="meshes",
        )
    """
    generator = URDFGenerator(model)
    robot = generator.generate(robot_name, mesh_dir=mesh_dir)

    if output_path:
        robot.save(output_path)

    return robot
