use rand::Rng;

fn main() {
    let mut rng: i32 = rand::thread_rng().gen_range(1..=30);
    println!("Weapon {:02}", rng);
}