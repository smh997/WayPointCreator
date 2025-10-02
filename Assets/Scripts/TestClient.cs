using System.Net.Sockets;
using System.Text;
using UnityEngine;

public class TestClient : MonoBehaviour
{
    public string serverIP = "192.168.0.100"; // PC IP from router
    public int serverPort = 5000;

    void Start()
    {
        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                string message = "Hello from HoloLens!";
                byte[] data = Encoding.UTF8.GetBytes(message);
                stream.Write(data, 0, data.Length);
                Debug.Log("Sent: " + message);

                byte[] buffer = new byte[1024];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                string response = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                Debug.Log("Received: " + response);
            }
        }
        catch (SocketException e)
        {
            Debug.LogError("Connection failed: " + e.Message);
        }
    }
}
