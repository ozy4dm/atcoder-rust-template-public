// AHC Human Only 向け・コンテスト前に準備する共通部品。
// 公開予定先（実際に公開済みであることを開始前に確認する）:
// https://github.com/ozy4dm/atcoder-rust-template-public/tree/main/ahc-human
// コピーして使う部品にも、この参照URLを残す。
#![allow(dead_code)]

use std::io::{self, Read};
use std::time::Instant;

// 非対話型専用。標準入力の終端まで一括で読む。
pub struct Scanner {
    tokens: std::vec::IntoIter<String>,
}

impl Scanner {
    pub fn new() -> Self {
        let mut text = String::new();
        io::stdin().read_to_string(&mut text).unwrap();
        Self::from_text(&text)
    }

    pub fn from_text(text: &str) -> Self {
        Self {
            tokens: text
                .split_whitespace()
                .map(str::to_owned)
                .collect::<Vec<_>>()
                .into_iter(),
        }
    }

    pub fn next<T: std::str::FromStr>(&mut self) -> T {
        self.tokens
            .next()
            .expect("入力が不足しています")
            .parse()
            .unwrap_or_else(|_| panic!("入力の型が合いません"))
    }
}

pub struct Timer {
    start: Instant,
    limit: f64,
}

impl Timer {
    pub fn new(limit_seconds: f64) -> Self {
        assert!(limit_seconds.is_finite() && limit_seconds > 0.0);
        Self {
            start: Instant::now(),
            limit: limit_seconds,
        }
    }

    pub fn elapsed(&self) -> f64 {
        self.start.elapsed().as_secs_f64()
    }

    pub fn progress(&self) -> f64 {
        (self.elapsed() / self.limit).clamp(0.0, 1.0)
    }

    pub fn is_over(&self) -> bool {
        self.elapsed() >= self.limit
    }
}

// SplitMix64。固定seedで乱数列を再現できる。暗号用途には使わない。
pub struct Rng {
    state: u64,
}

impl Rng {
    pub fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }

    // 0以上upper未満。剰余による偏りを棄却で取り除く。
    pub fn index(&mut self, upper: usize) -> usize {
        assert!(upper > 0, "空の候補からは選べません");
        let bound = upper as u64;
        let threshold = bound.wrapping_neg() % bound;
        loop {
            let value = self.next_u64();
            if value >= threshold {
                return (value % bound) as usize;
            }
        }
    }

    // 0以上1未満。確率判定用。
    pub fn unit(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / ((1u64 << 53) as f64)
    }

    pub fn shuffle<T>(&mut self, values: &mut [T]) {
        for i in (1..values.len()).rev() {
            values.swap(i, self.index(i + 1));
        }
    }
}

// 幾何冷却。開始温度・終了温度は「評価値の差」の大きさに合わせる。
pub fn temperature(start: f64, end: f64, progress: f64) -> f64 {
    assert!(start.is_finite() && start > 0.0);
    assert!(end.is_finite() && end > 0.0);
    assert!(progress.is_finite());
    let p = progress.clamp(0.0, 1.0);
    ((1.0 - p) * start.ln() + p * end.ln()).exp()
}

// gainは「改善なら正」。最大化では新-旧、最小化では旧-新を渡す。
// temp=0は山登り法（同点も受理）。非有限の値や負の温度は実装ミスとして検出。
pub fn accept(gain: f64, temp: f64, rng: &mut Rng) -> bool {
    assert!(gain.is_finite());
    assert!(temp.is_finite() && temp >= 0.0);
    gain >= 0.0 || (temp > 0.0 && rng.unit() < (gain / temp).exp())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scanner_reads_whitespace_and_types() {
        let mut sc = Scanner::from_text("3\r\n -7  2.5\nabc");
        assert_eq!(sc.next::<usize>(), 3);
        assert_eq!(sc.next::<i64>(), -7);
        assert_eq!(sc.next::<f64>(), 2.5);
        assert_eq!(sc.next::<String>(), "abc");
    }

    #[test]
    fn random_sequence_is_repeatable_and_bounded() {
        let mut a = Rng::new(42);
        let mut b = Rng::new(42);
        for _ in 0..1000 {
            assert_eq!(a.next_u64(), b.next_u64());
        }
        let mut rng = Rng::new(0);
        for bound in [1, 2, 3, 100, usize::MAX] {
            for _ in 0..1000 {
                assert!(rng.index(bound) < bound);
                assert!((0.0..1.0).contains(&rng.unit()));
            }
        }
        let mut values: Vec<_> = (0..100).collect();
        rng.shuffle(&mut values);
        values.sort();
        assert_eq!(values, (0..100).collect::<Vec<_>>());
        rng.shuffle::<usize>(&mut []);
    }

    #[test]
    fn cooling_and_acceptance_have_expected_direction() {
        assert!((temperature(100.0, 1.0, 0.0) - 100.0).abs() < 1e-10);
        assert!((temperature(100.0, 1.0, 0.5) - 10.0).abs() < 1e-10);
        assert!((temperature(100.0, 1.0, 1.0) - 1.0).abs() < 1e-10);
        let mut rng = Rng::new(123);
        assert!(accept(1.0, 0.0, &mut rng));
        assert!(accept(0.0, 0.0, &mut rng));
        assert!(!accept(-1.0, 0.0, &mut rng));
        let count = (0..20000).filter(|_| accept(-1.0, 1.0, &mut rng)).count();
        assert!((6800..7900).contains(&count)); // e^-1 ≈ 0.368
    }

    #[test]
    fn timer_progress_is_bounded() {
        let timer = Timer::new(60.0);
        assert!((0.0..=1.0).contains(&timer.progress()));
        let expired = Timer {
            start: Instant::now() - std::time::Duration::from_secs(2),
            limit: 1.0,
        };
        assert!(expired.is_over());
        assert_eq!(expired.progress(), 1.0);
    }
}
