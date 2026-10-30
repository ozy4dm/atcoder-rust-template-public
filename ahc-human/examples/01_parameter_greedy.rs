// 型1: 重み → 貪欲で完成計画を生成 → 正式な評価で選ぶ。
mod delivery;
fn main() {
    let problem = delivery::sample();
    let mut best = problem.greedy_order(0.0);
    for weight in [0.0, 0.25, 0.5, 1.0, 2.0, 4.0] {
        let candidate = problem.greedy_order(weight);
        if problem.cost(&candidate) < problem.cost(&best) { best = candidate; }
    }
    problem.show(&best);
}
