#![doc = include_str!("../README.md")]
#![forbid(unsafe_code)]
#![cfg_attr(docsrs, feature(doc_cfg))]
#![cfg_attr(docsrs, allow(unused_attributes))]
#![deny(missing_docs)]

use std::sync::OnceLock;

use rustix::net::{bind, ipproto, socket, sockopt::set_ipv6_v6only, AddressFamily, SocketType};

static INIT: OnceLock<Probe> = OnceLock::new();

const V6_PROBES: [(bool, bool); 2] = [
  (true, true),   // IPv6
  (false, false), // IPv4-mapped
];

/// Returns `true` if the system supports IPv4 communication.
pub fn ipv4() -> bool {
  probe().ipv4
}

/// Returns `true` if the system supports IPv6 communication.
pub fn ipv6() -> bool {
  probe().ipv6
}

/// Returns `true` if the system understands
/// IPv4-mapped IPv6.
pub fn ipv4_mapped_ipv6() -> bool {
  probe().ipv4_mapped_ipv6
}

/// Represents the IP stack communication capabilities of the system.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct Probe {
  ipv4: bool,
  ipv6: bool,
  ipv4_mapped_ipv6: bool,
}

impl Probe {
  /// Returns `true` if the system supports IPv4 communication.
  #[inline]
  pub const fn ipv4(&self) -> bool {
    self.ipv4
  }

  /// Returns `true` if the system supports IPv6 communication.
  #[inline]
  pub const fn ipv6(&self) -> bool {
    self.ipv6
  }

  /// Returns `true` if the system understands
  /// IPv4-mapped IPv6.
  #[inline]
  pub const fn ipv4_mapped_ipv6(&self) -> bool {
    self.ipv4_mapped_ipv6
  }
}

/// Probes IPv4, IPv6 and IPv4-mapped IPv6 communication
/// capabilities which are controlled by the `IPV6_V6ONLY` socket option
/// and kernel configuration.
///
/// Should we try to use the IPv4 socket interface if we're only
/// dealing with IPv4 sockets? As long as the host system understands
/// IPv4-mapped IPv6, it's okay to pass IPv4-mapped IPv6 addrs to
/// the IPv6 interface. That simplifies our code and is most
/// general. Unfortunately, we need to run on kernels built without
/// IPv6 support too. So probe the kernel to figure it out.
pub fn probe() -> Probe {
  *INIT.get_or_init(probe_in)
}

// #[cfg(unix)]
fn probe_in() -> Probe {
  use std::net::{Ipv6Addr, SocketAddrV6};

  let mut caps = Probe {
    ipv4: false,
    ipv6: false,
    ipv4_mapped_ipv6: false,
  };

  #[cfg(windows)]
  let _ = rustix::net::wsa_startup();

  // Check IPv4 support
  {
    let ipv4_sock = socket(AddressFamily::INET, SocketType::STREAM, Some(ipproto::TCP));

    if ipv4_sock.is_ok() {
      caps.ipv4 = true;
    }
  }

  // Probe IPv6 and IPv4-mapped IPv6
  for (is_ipv6, v6_only) in V6_PROBES {
    let sock = socket(AddressFamily::INET6, SocketType::STREAM, Some(ipproto::TCP));

    if let Ok(sock) = sock {
      // Set IPV6_V6ONLY option
      let _ = set_ipv6_v6only(&sock, v6_only);

      // Create bind address
      let addr = if is_ipv6 {
        SocketAddrV6::new(Ipv6Addr::LOCALHOST, 0, 0, 0)
      } else {
        SocketAddrV6::new(
          // ::ffff:127.0.0.1
          Ipv6Addr::new(0, 0, 0, 0, 0, 0xffff, 0x7f00, 0x01),
          0,
          0,
          0,
        )
      };

      // Attempt to bind
      let bind_result = bind(sock, &addr.into());

      if bind_result.is_ok() {
        if is_ipv6 {
          caps.ipv6 = true;
        } else {
          caps.ipv4_mapped_ipv6 = true;
        }
      }
    }
  }

  #[cfg(windows)]
  let _ = rustix::net::wsa_cleanup();

  caps
}

#[test]
fn test() {
  let caps = probe();
  println!("IPv4 enabled: {}", caps.ipv4());
  println!("IPv6 enabled: {}", caps.ipv6());
  println!("IPv4-mapped IPv6 enabled: {}", caps.ipv4_mapped_ipv6());
}
