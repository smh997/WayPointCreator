# AURaPath — Augmented Reality Waypoint determination for UR10 Robots

**AURaPath** is an end-to-end augmented reality system for **spatial waypoint determination, digital-twin preview, and execution** on a physical **Universal Robots UR10** collaborative robot using **Microsoft HoloLens 2**.

This repository contains the **full implementation used in our IEEE paper**, including:
- A Unity-based AR application for HoloLens 2
- A PC-based middleware server for robot communication
- Live execution on a physical UR10 robot

> 🔗 This repository accompanies the paper  
> **“Human–Robot Interaction for Robot Programming using Augmented Reality and Digital Twin”**

---

## 🎥 Demo — Real System, Real Robot

### End-to-End Video Demonstration
*(Waypoint Determination → Preview → Execute)*

📹 **Demo video placeholder**  
(Add link here)

---

### System in Use (Representative Figures)

These images correspond directly to the system described and demonstrated in the paper.

**Figure 1 — AR Waypoint Determination**  
Users place and edit 6-DoF waypoints directly in 3D space using hand interaction on HoloLens 2.

📷 *(Insert image: AR scene with waypoints and UR10 digital twin)*

---

**Figure 2 — Digital Twin Preview (Preview-before-Execute)**  
The authored trajectory is animated on a synchronized UR10 digital twin before execution.

📷 *(Insert image: animated trajectory preview)*

---

**Figure 3 — Physical Execution on UR10**  
The validated trajectory is executed on the real UR10 robot in a lab workspace.

📷 *(Insert image: UR10 executing trajectory)*

---

## 🧠 System Overview

AURaPath enables users to **select robot motion directly in the workspace** using augmented reality rather than traditional teach pendants or offline programming tools.

The system follows a structured, multi-stage workflow that makes the author–validate–execute pipeline explicit to the user:

1. **Configuration**  
   Users register and position the UR10 digital twin within the AR environment.  
   The digital twin can be spatially aligned with the physical robot for in-situ programming, or placed elsewhere (e.g., on a nearby table).

2. **Determining Trajectory**  
   Users place and edit 6-DoF end-effector waypoints relative to the digital twin using hand-based interaction.  
   Waypoints define the desired robot motion and can be iteratively refined.

3. **Preview**  
   The authored trajectory is validated and visually inspected using an animated digital twin, enabling preview-before-execute verification without moving the physical robot.

4. **Execute**  
   The validated trajectory is transmitted to the PC middleware server and executed on the physical UR10 robot.

This workflow supports intuitive spatial programming while reducing trial-and-error and improving safety in collaborative environments.

---

## 🏗️ System Architecture


### HoloLens 2 (AR Client)
- Unity application built with Mixed Reality Toolkit (MRTK)
- Provides hand-based interaction for waypoint placement and editing
- Visualizes a UR10 digital twin and trajectory previews
- Serializes waypoint data and transmits it to the PC server over Wi-Fi

### PC Middleware Server
- Receives waypoint data from the AR client
- Transforms poses from the AR coordinate frame into the UR10 base frame
- Performs reachability checking before preview or execution
- Generates and sends executable robot commands via URSocket / RTDE

### UR10 Robot
- Executes validated waypoint trajectories on physical hardware
- Reports joint state to initialize and synchronize the digital twin

This separation allows the AR device to focus on interaction and visualization, while the PC server handles robot-specific computation and execution.

---

## 🧰 Hardware Requirements

The current implementation of AURaPath has been validated using the following hardware:

- **Microsoft HoloLens 2**
  - Used for AR interaction, waypoint authoring, and digital twin visualization
- **Universal Robots UR10**
  - 6-DoF collaborative robotic arm
  - Ethernet-enabled controller
- **PC / Laptop (Middleware Server)**
  - Connected to the UR10 via Ethernet
  - Connected to the HoloLens 2 via Wi-Fi
  - Used for trajectory validation and robot command execution

> ⚠️ At present, the system supports **UR10 only**. Adapting to other robot platforms would require changes to the kinematic model and communication interface.

---

## 💻 Software Requirements

### AR Client (HoloLens 2)
- **Unity** (with Universal Windows Platform support enabled)
- **Mixed Reality Toolkit (MRTK)** for HoloLens 2
- **Windows SDK** compatible with HoloLens 2 deployment
- Visual Studio (for UWP build and deployment)

### PC Middleware Server
- **Python** or **C# (.NET)** runtime (depending on server implementation)
- **URSocket / RTDE** access enabled on the UR10 controller
- Network access to the robot controller over Ethernet

### Robot
- **UR10 PolyScope** (standard installation)
- Network communication enabled

---

## ⚙️ Setup Instructions

### 1. UR10 Robot Setup
1. Power on the UR10 robot and controller
2. Ensure the robot is in a mode that allows external control
3. Connect the robot controller to the PC via Ethernet
4. Note the robot IP address (static IP is recommended)

---

### 2. PC Middleware Server Setup

(TODO)
<!-- ```bash
cd Server
pip install -r requirements.txt
python server.py
-->


