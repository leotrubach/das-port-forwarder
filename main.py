import paramiko
import os
import threading
import socket
import select
from dotenv import load_dotenv

# Load settings from .env
load_dotenv()

SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER")
SSH_PASS = os.getenv("SSH_PASS")
LOCAL_PORT = int(os.getenv("LOCAL_PORT", 8080))
REMOTE_PORT = int(os.getenv("REMOTE_PORT", 8080))


class SSHTunnel:
    def __init__(self, local_port, remote_port, ssh_host, ssh_port, ssh_user, ssh_pass):
        self.local_port = local_port
        self.remote_port = remote_port
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.ssh_client = None
        self.running = True

    def connect_ssh(self):
        """Establish an SSH connection."""
        while self.running:
            try:
                print(f"Connecting to {self.ssh_host}:{self.ssh_port} as {self.ssh_user}...")
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh_client.connect(self.ssh_host, port=self.ssh_port, username=self.ssh_user,
                                        password=self.ssh_pass)
                print("SSH Connection established.")
                return self.ssh_client
            except Exception as e:
                print(f"SSH connection failed: {e}. Retrying in 5 seconds...")
                self.ssh_client = None
                time.sleep(5)

    def forward_tunnel(self):
        """Handles the port forwarding logic."""
        while self.running:
            self.ssh_client = self.connect_ssh()
            transport = self.ssh_client.get_transport()
            if not transport:
                print("Failed to get transport. Retrying...")
                time.sleep(5)
                continue

            try:
                transport.request_port_forward("127.0.0.1", self.remote_port)
                print(
                    f"Tunnel established: remote {self.ssh_host}:{self.remote_port} -> local 127.0.0.1:{self.local_port}")

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("127.0.0.1", self.local_port))
                    sock.listen(5)
                    print(f"Listening on 127.0.0.1:{self.local_port}... Press Ctrl+C to stop.")

                    while self.running:
                        try:
                            client_socket, addr = sock.accept()
                            threading.Thread(target=self.handle_connection, args=(client_socket, transport)).start()
                        except Exception as e:
                            print(f"Socket error: {e}")
                            break
            except Exception as e:
                print(f"Error in tunnel: {e}. Restarting...")
                time.sleep(5)

    def handle_connection(self, client_socket, transport):
        """Handles a single connection."""
        try:
            remote_socket = transport.open_channel("direct-tcpip", ("127.0.0.1", self.remote_port),
                                                   client_socket.getpeername())
            if remote_socket is None:
                print("Failed to open channel")
                client_socket.close()
                return

            while self.running:
                r, _, _ = select.select([client_socket, remote_socket], [], [])
                if client_socket in r:
                    data = client_socket.recv(1024)
                    if not data:
                        break
                    remote_socket.sendall(data)
                if remote_socket in r:
                    data = remote_socket.recv(1024)
                    if not data:
                        break
                    client_socket.sendall(data)
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            client_socket.close()
            remote_socket.close()

    def stop_tunnel(self):
        """Stops the tunnel gracefully."""
        self.running = False
        if self.ssh_client:
            self.ssh_client.close()
        print("Tunnel closed.")


if __name__ == "__main__":
    tunnel = SSHTunnel(LOCAL_PORT, REMOTE_PORT, SSH_HOST, SSH_PORT, SSH_USER, SSH_PASS)
    try:
        tunnel.forward_tunnel()
    except KeyboardInterrupt:
        print("\nShutting down...")
        tunnel.stop_tunnel()
