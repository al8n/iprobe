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

/// Returns `true` if the host can create an IPv4 TCP socket.
pub fn ipv4() -> bool {
  probe().ipv4
}

/// Returns `true` if the host can create an IPv6 TCP socket and bind it to
/// the IPv6 loopback address (`::1`).
pub fn ipv6() -> bool {
  probe().ipv6
}

/// Returns `true` if the host can create a dual-stack IPv6 TCP socket and bind
/// it to the IPv4-mapped loopback address (`::ffff:127.0.0.1`).
pub fn ipv4_mapped_ipv6() -> bool {
  probe().ipv4_mapped_ipv6
}

/// A cached, best-effort snapshot of local IP socket operation support.
///
/// The snapshot records socket creation and loopback binding only. It does
/// not indicate routing, interface availability, remote-host reachability, or
/// Internet connectivity. A `false` result can reflect unsupported
/// functionality, policy restrictions, resource exhaustion, or a transient
/// failure.
#[derive(Debug, Copy, Clone, PartialEq, Eq)]
pub struct Probe {
  ipv4: bool,
  ipv6: bool,
  ipv4_mapped_ipv6: bool,
}

impl Probe {
  /// Returns `true` if the host can create an IPv4 TCP socket.
  #[inline]
  pub const fn ipv4(&self) -> bool {
    self.ipv4
  }

  /// Returns `true` if the host can create an IPv6 TCP socket and bind it to
  /// the IPv6 loopback address (`::1`).
  #[inline]
  pub const fn ipv6(&self) -> bool {
    self.ipv6
  }

  /// Returns `true` if the host can create a dual-stack IPv6 TCP socket and
  /// bind it to the IPv4-mapped loopback address (`::ffff:127.0.0.1`).
  #[inline]
  pub const fn ipv4_mapped_ipv6(&self) -> bool {
    self.ipv4_mapped_ipv6
  }
}

/// Probes local IPv4, IPv6, and IPv4-mapped IPv6 socket operations once per
/// process and returns the cached snapshot on subsequent calls.
///
/// The IPv4 probe creates an IPv4 TCP socket. The IPv6 probe creates an IPv6
/// TCP socket and binds it to `::1`. The IPv4-mapped IPv6 probe creates a
/// dual-stack IPv6 TCP socket and binds it to `::ffff:127.0.0.1`.
///
/// These checks do not test routing, interface availability, remote hosts, or
/// Internet connectivity. A `false` result is best effort and can reflect
/// unsupported functionality, policy restrictions, resource exhaustion, or a
/// transient failure.
pub fn probe() -> Probe {
  *INIT.get_or_init(probe_in)
}

fn probe_in() -> Probe {
  use std::net::{Ipv6Addr, SocketAddrV6};

  let mut caps = Probe {
    ipv4: false,
    ipv6: false,
    ipv4_mapped_ipv6: false,
  };

  #[cfg(windows)]
  if rustix::net::wsa_startup().is_err() {
    // Without successful process-wide Winsock initialization, no probe is valid.
    return caps;
  }

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
      // The bind below is the effective usability check if setting this option
      // is unsupported or restricted.
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
      let bind_result = bind(sock, &addr);

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
  {
    // Pair the successful process-wide WSAStartup call; cleanup is not reached
    // when startup fails.
    let _ = rustix::net::wsa_cleanup();
  }

  caps
}

#[cfg(test)]
mod tests {
  use super::*;

  #[test]
  fn accessors_reflect_fields() {
    let complementary = Probe {
      ipv4: true,
      ipv6: false,
      ipv4_mapped_ipv6: true,
    };

    assert!(complementary.ipv4());
    assert!(!complementary.ipv6());
    assert!(complementary.ipv4_mapped_ipv6());

    let opposite = Probe {
      ipv4: false,
      ipv6: true,
      ipv4_mapped_ipv6: false,
    };

    assert!(!opposite.ipv4());
    assert!(opposite.ipv6());
    assert!(!opposite.ipv4_mapped_ipv6());
  }

  #[test]
  fn probe_is_cached_and_free_functions_match() {
    let first = probe();
    let second = probe();

    assert_eq!(first, second);
    assert_eq!(first.ipv4(), ipv4());
    assert_eq!(first.ipv6(), ipv6());
    assert_eq!(first.ipv4_mapped_ipv6(), ipv4_mapped_ipv6());
  }
}
