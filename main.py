import paramiko
import os
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

    def start_tunnel(self):
        try:
            print(f"Connecting to {self.ssh_host}:{self.ssh_port} as {self.ssh_user}...")
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(self.ssh_host, port=self.ssh_port, username=self.ssh_user, password=self.ssh_pass)

            transport = self.ssh_client.get_transport()
            if not transport:
                print("Failed to get SSH transport")
                return

            # Open a reverse SSH tunnel
            transport.request_port_forward("", self.remote_port)
            print(f"Tunnel established: localhost:{self.local_port} → {self.ssh_host}:{self.remote_port}")

            # Forwarding loop
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", self.local_port))
                sock.listen(5)

                print(f"Listening on localhost:{self.local_port}... Press Ctrl+C to stop.")
                while True:
                    client_socket, addr = sock.accept()
                    self.handle_connection(client_socket, transport)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.stop_tunnel()

    def handle_connection(self, client_socket, transport):
        """Handles a single connection."""
        try:
            remote_socket = transport.open_channel("direct-tcpip", ("127.0.0.1", self.remote_port), client_socket.getpeername())
            if remote_socket is None:
                print("Failed to open channel")
                return

            # Forward data between local and remote
            while True:
                r, w, x = select.select([client_socket, remote_socket], [], [])
                if client_socket in r:
                    data = client_socket.recv(1024)
                    if len(data) == 0:
                        break
                    remote_socket.sendall(data)
                if remote_socket in r:
                    data = remote_socket.recv(1024)
                    if len(data) == 0:
                        break
                    client_socket.sendall(data)

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            client_socket.close()
            remote_socket.close()

    def stop_tunnel(self):
        if self.ssh_client:
            self.ssh_client.close()
            print("Tunnel closed.")

if __name__ == "__main__":
    tunnel = SSHTunnel(LOCAL_PORT, REMOTE_PORT, SSH_HOST, SSH_PORT, SSH_USER, SSH_PASS)
    try:
        tunnel.start_tunnel()
    except KeyboardInterrupt:
        print("\nShutting down...")
        tunnel.stop_tunnel()
