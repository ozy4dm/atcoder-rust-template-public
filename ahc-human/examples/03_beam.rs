// 型3: 途中計画の集団 → 全候補へ展開 → 評価 → 上位だけ残す。
mod delivery;
#[derive(Clone)]
struct State { order: Vec<usize>, used: u64, cost: i64 }
fn main() {
    let problem = delivery::sample();
    assert!(problem.jobs.len() <= 64);
    let width = 32;
    let mut beam = vec![State { order: vec![], used: 0, cost: 0 }];
    for _depth in 0..problem.jobs.len() {
        let mut next = Vec::new();
        for state in &beam {
            for id in 0..problem.jobs.len() {
                if state.used & (1u64 << id) != 0 { continue; }
                let mut child = state.clone();
                child.order.push(id);
                child.used |= 1u64 << id;
                child.cost = problem.cost(&child.order);
                next.push(child);
            }
        }
        // 同じ深さを比較。実問題では残り費用の見積もり等も検討する。
        next.sort_by_key(|s| s.cost);
        next.truncate(width);
        beam = next;
    }
    let best = beam.iter().min_by_key(|s| s.cost).unwrap();
    problem.show(&best.order);
}
