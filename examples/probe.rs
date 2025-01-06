use iprobe::{ipv4, ipv4_mapped_ipv6, ipv6};

fn main() {
  println!("IPv4 enabled: {}", ipv4());
  println!("IPv6 enabled: {}", ipv6());
  println!("IPv4-mapped IPv6 enabled: {}", ipv4_mapped_ipv6());
}
