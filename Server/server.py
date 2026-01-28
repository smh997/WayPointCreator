import socket
import json
import URsocket.UR as UR

robot_ip = "192.168.1.20"

HOST = "192.168.0.100"
PORT = 5000

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(1)
        print(f"Server listening on {HOST}:{PORT}")

        while True:
            conn, addr = server_socket.accept()
            with conn:
                print(f"Connected by {addr}")

                try:
                    robot = UR.control(robot_ip)
                    tcp_offset = robot.getTCPOffset()
                    current_joints = robot.getActualJointPositions()

                    # --- NO MORE auto-sending robot state ---
                    # Unity will explicitly request it with {"type":"robot_state"}

                    while True:
                        # --- Read message until newline ---
                        data = b""
                        while True:
                            chunk = conn.recv(1024)
                            if not chunk or chunk.endswith(b"\n"):
                                data += chunk
                                break
                            data += chunk

                        if not data:
                            print("Client disconnected")
                            break

                        message = data.decode("utf-8").strip()
                        print("Received:", message)

                        try:
                            msg_obj = json.loads(message)
                            msg_type = msg_obj.get("type", "").lower()

                            # ====================================================
                            #  REQUEST: ROBOT STATE
                            # ====================================================
                            if msg_type == "robot_state":
                                robot_state = {
                                    "joints": robot.getActualJointPositions(False),
                                    "tcp": robot.getActualTCPPose()
                                }
                                conn.sendall((json.dumps(robot_state) + "\n").encode("utf-8"))
                                continue

                            # ====================================================
                            #  PREVIEW TRAJECTORY
                            # ====================================================
                            if msg_type == "preview":
                                waypoints = msg_obj.get("waypoints", [])
                                joint_solutions = []
                                error_msgs = []
                                temp_joints = current_joints.copy()
                                tcp = robot.getActualTCPPose()

                                for i, wp in enumerate(waypoints):
                                    target = [
                                        wp["x"], wp["y"], wp["z"],
                                        tcp[3],
                                        tcp[4],
                                        tcp[5]
                                    ]

                                    if robot.getInverseKinSol(target, temp_joints, 1e-3, 1e-3, tcp_offset):
                                        q_sol = robot.getInverseKin(target, temp_joints, 1e-3, 1e-3, tcp_offset)
                                        joint_solutions.append(q_sol)
                                        temp_joints = q_sol
                                    else:
                                        error_msgs.append(f"Waypoint {i} unreachable.")

                                response = {
                                    "success": len(error_msgs) == 0,
                                    "message": "; ".join(error_msgs) if error_msgs else "All waypoints reachable.",
                                    "jointSolutions": [{"joints": sol} for sol in joint_solutions]
                                }
                                
                                print("Response:", response)
                                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                                continue

                            # ====================================================
                            #  RUN TRAJECTORY
                            # ====================================================
                            if msg_type == "run":
                                waypoints = msg_obj.get("waypoints", [])
                                candidate_poses = []
                                error_msgs = []
                                temp_joints = current_joints.copy()
                                tcp = robot.getActualTCPPose()

                                for i, wp in enumerate(waypoints):
                                    target = [
                                        wp["x"], wp["y"], wp["z"],
                                        tcp[3],
                                        tcp[4],
                                        tcp[5]
                                    ]

                                    if robot.getInverseKinSol(target, temp_joints, 1e-3, 1e-3, tcp_offset):
                                        q_sol = robot.getInverseKin(target, temp_joints, 1e-3, 1e-3, tcp_offset)
                                        candidate_poses.append(q_sol)
                                        temp_joints = q_sol
                                    else:
                                        error_msgs.append(f"Waypoint {i} unreachable.")

                                if not error_msgs:
                                    for sol in candidate_poses:
                                        robot.moveJ(sol, 0.5, 0.2, 0, 0)
                                        current_joints = robot.getActualJointPositions()
                                
                                robot_state = {
                                    "joints": robot.getActualJointPositions(False),
                                    "tcp": robot.getActualTCPPose()
                                }
                                response = {
                                    "success": len(error_msgs) == 0,
                                    "message": "; ".join(error_msgs) if error_msgs else "Trajectory executed.",
                                    "robotState": robot_state
                                }
                                print("Response:", response)
                                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                                continue

                            # ====================================================
                            #  UNKNOWN MESSAGE
                            # ====================================================
                            response = {"success": False, "message": "Unknown request type."}
                            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

                        except json.JSONDecodeError:
                            response = {"success": False, "message": "Invalid JSON format."}
                            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

                    robot.disconnect()

                except Exception as e:
                    print("Error communicating with robot:", e)

if __name__ == "__main__":
    start_server()
