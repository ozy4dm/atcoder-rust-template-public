// 特定の大会に依存しない、小さな練習用運搬問題。
// 障害物なし、1個だけ運べる。移動1歩・拾う・置くが各1手。
#![allow(dead_code)]
#[derive(Clone, Copy, Debug)]
pub struct Point { pub x: i32, pub y: i32 }
#[derive(Clone, Copy)]
pub struct Job { pub pickup: Point, pub destination: Point }
pub struct Problem { pub start: Point, pub jobs: Vec<Job> }
#[derive(Debug)]
pub enum Action { Right, Left, Up, Down, Pickup(usize), Drop(usize) }
fn distance(a: Point, b: Point) -> i64 {
    (a.x - b.x).abs() as i64 + (a.y - b.y).abs() as i64
}
pub fn sample() -> Problem {
    let p = |x, y| Point { x, y };
    Problem { start: p(0, 0), jobs: vec![
        Job { pickup: p(1, 0), destination: p(9, 2) },
        Job { pickup: p(2, 1), destination: p(0, 3) },
        Job { pickup: p(8, 1), destination: p(4, 5) },
        Job { pickup: p(4, 4), destination: p(1, 2) },
        Job { pickup: p(0, 5), destination: p(7, 4) },
    ] }
}
impl Problem {
    // 計画は「運搬順」。歩く操作は持たない。
    pub fn greedy_order(&self, delivery_weight: f64) -> Vec<usize> {
        let mut order = Vec::new();
        let mut used = vec![false; self.jobs.len()];
        let mut at = self.start;
        while order.len() < self.jobs.len() {
            let id = (0..self.jobs.len()).filter(|&i| !used[i]).min_by(|&a, &b| {
                let value = |i: usize| distance(at, self.jobs[i].pickup) as f64
                    + delivery_weight * distance(self.jobs[i].pickup, self.jobs[i].destination) as f64;
                value(a).total_cmp(&value(b))
            }).unwrap();
            used[id] = true;
            order.push(id);
            at = self.jobs[id].destination;
        }
        order
    }
    // 正式な手数。探索中は1歩ずつ再生せず距離で計算する。
    pub fn cost(&self, order: &[usize]) -> i64 {
        let mut at = self.start;
        let mut cost = 0;
        for &i in order {
            let j = self.jobs[i];
            cost += distance(at, j.pickup) + 1 + distance(j.pickup, j.destination) + 1;
            at = j.destination;
        }
        cost
    }
    // 最後に一度だけ、計画を1アクションずつの列へ変換する。
    pub fn expand(&self, order: &[usize]) -> Vec<Action> {
        fn walk(at: &mut Point, to: Point, out: &mut Vec<Action>) {
            while at.x < to.x { out.push(Action::Right); at.x += 1; }
            while at.x > to.x { out.push(Action::Left); at.x -= 1; }
            while at.y < to.y { out.push(Action::Up); at.y += 1; }
            while at.y > to.y { out.push(Action::Down); at.y -= 1; }
        }
        let mut at = self.start;
        let mut out = Vec::new();
        for &id in order {
            walk(&mut at, self.jobs[id].pickup, &mut out);
            out.push(Action::Pickup(id));
            walk(&mut at, self.jobs[id].destination, &mut out);
            out.push(Action::Drop(id));
        }
        out
    }
    pub fn show(&self, order: &[usize]) {
        let mut sorted = order.to_vec(); sorted.sort_unstable();
        assert_eq!(sorted, (0..self.jobs.len()).collect::<Vec<_>>());
        let actions = self.expand(order);
        assert_eq!(self.cost(order), actions.len() as i64);
        println!("order={order:?}\ncost={}\nactions={actions:?}", self.cost(order));
    }
}
