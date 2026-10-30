// 型2: 完成計画 → 順序の変更 → 評価 → 採用／取り消し。
#[path = "../library.rs"] mod ahc;
mod delivery;
fn main() {
    let problem = delivery::sample();
    let mut rng = ahc::Rng::new(42);
    let mut current = problem.greedy_order(0.0);
    let mut score = problem.cost(&current);
    let mut best = current.clone();
    let mut best_score = score;
    // 見本は再現できる固定回数。本番では必要に応じてTimerを使う。
    for step in 0..10_000 {
        let a = rng.index(current.len());
        let b = rng.index(current.len());
        current.swap(a, b);
        let next_score = problem.cost(&current); // まず全体評価。差分化は後から。
        let gain = (score - next_score) as f64; // 最小化なので「旧−新」
        let temp = ahc::temperature(5.0, 0.1, step as f64 / 10_000.0);
        if ahc::accept(gain, temp, &mut rng) {
            score = next_score;
            if score < best_score { best_score = score; best = current.clone(); }
        } else {
            current.swap(a, b);
        }
    }
    problem.show(&best); // 最後のcurrentではなく最良計画を展開。
}
