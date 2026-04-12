import java.net.http.HttpClient;
import java.net.http.HttpRequest;
public class Agent {
    public void run() {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .GET()
            .build();
    }
}
