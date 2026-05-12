
# Reference Implementations: WHATWG URLPattern Standard

The URLPattern standard is a significant leap beyond simple regex or string prefix matching. It requires a parser for the pattern syntax itself, a component-based matching logic (protocol, hostname, pathname, etc.), and support for "canonicalization" where patterns are normalized before matching.

Below are the most robust, high-performance implementations currently available.


## 1. Ada (C++) — The Performance Leader

**Ada** is arguably the fastest spec-compliant URL library in the world. It is the default URL engine for **Node.js** (since v18) and is used by Cloudflare Workers and Bun. While primarily a URL parser, it contains a full, standalone URLPattern implementation.



* **Repository:** [ada-url/ada](https://github.com/ada-url/ada)
* **Key Directory:** src/urlpattern
* **Strengths:** * Written in modern C++ (C++20).
    * Uses SIMD instructions for extreme speed.
    * Specifically validated against the WPT urlpattern suite.
    * **Direct Path:** [ada/src/urlpattern.cpp](https://github.com/ada-url/ada/blob/main/src/urlpattern.cpp) contains the core matching engine.


## 2. Blink / Chromium (C++) — The Source of Truth

This is the implementation used by Google Chrome. If a pattern works here, it is by definition "correct" according to the standard's primary stakeholder.



* **Repository:** [Chromium Source](https://chromium.googlesource.com/chromium/src/)
* **Key Directory:** third_party/blink/renderer/core/url_pattern
* **Strengths:**
    * The most battle-tested code in existence.
    * Handles all edge cases of the WebIDL bindings and component normalization.
    * **Direct Path:** [blink/renderer/core/url_pattern/url_pattern.cc](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/url_pattern/url_pattern.cc).


## 3. rust-urlpattern (Rust) — The Deno Engine

Used internally by **Deno**, this crate is the gold standard for Rust developers. Deno requires total Web API compatibility, so their Rust implementation is rigorously tested.



* **Repository:** [denoland/rust-urlpattern](https://github.com/denoland/rust-urlpattern)
* **Strengths:**
    * Memory-safe and highly performant.
    * Can be used as a standalone crate in any Rust project.
    * Used as the base for many other language wrappers (like Ruby and Go).
    * **Direct Path:** The core logic is in src/lib.rs and src/parser.rs.


## 4. urlpattern-polyfill (JavaScript) — The Logic Reference

Maintained by the WICG (Web Incubator Community Group), this is the official polyfill. While not as fast as C++ or Rust, it is the most readable "reference" for how the logic should be implemented.



* **Repository:** [kenchris/urlpattern-polyfill](https://github.com/kenchris/urlpattern-polyfill)
* **Strengths:**
    * Deeply aligned with the spec's algorithmic steps.
    * Ideal for understanding the "Pattern Parser" vs. the "Matcher."
    * **Direct Path:** [src/index.ts](https://github.com/kenchris/urlpattern-polyfill/blob/main/src/index.ts).


### Implementation Scorecard (Spec Compliance)


<table>
  <tr>
   <td><strong>Implementation</strong>
   </td>
   <td><strong>Language</strong>
   </td>
   <td><strong>WPT Coverage</strong>
   </td>
   <td><strong>Best For</strong>
   </td>
  </tr>
  <tr>
   <td><strong>Ada</strong>
   </td>
   <td>C++
   </td>
   <td>>99%
   </td>
   <td>High-performance backends / C-FFI
   </td>
  </tr>
  <tr>
   <td><strong>Blink</strong>
   </td>
   <td>C++
   </td>
   <td>100%
   </td>
   <td>Reference behavior / Browsers
   </td>
  </tr>
  <tr>
   <td><strong>Deno</strong>
   </td>
   <td>Rust
   </td>
   <td>>99%
   </td>
   <td>Cloud runtimes / Rust apps
   </td>
  </tr>
  <tr>
   <td><strong>Polyfill</strong>
   </td>
   <td>JS
   </td>
   <td>100%
   </td>
   <td>Frontend / Node.js logic
   </td>
  </tr>
</table>



### Recommendation for Python

Since Python lacks a native, high-quality port, the most "robust" path for a production system is:



1. **PyO3 Wrapper:** Use the [denoland/rust-urlpattern](https://github.com/denoland/rust-urlpattern) crate and wrap it using PyO3 to create a native Python module.
2. **Cython/CFFI:** Wrap [ada-url/ada](https://github.com/ada-url/ada).

This approach ensures you aren't relying on a "5-star repo" that might miss complex edge cases like IPv6 normalization or character-class escaping in the pattern parser.
