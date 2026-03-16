import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;

public class Agent {
    public static void main(String[] args) {
        String apiKey = System.getenv("API_KEY");
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.example.com/data"))
            .GET()
            .build();
        System.out.println("Agent running with key: " + apiKey);
    }

    public void run() {
        main(new String[]{});
    }
}
