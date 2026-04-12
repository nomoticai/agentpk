import java.io.FileWriter;
import java.io.FileReader;
public class Agent {
    public void run() {
        FileWriter writer = new FileWriter("out.txt");
        FileReader reader = new FileReader("in.txt");
    }
}
