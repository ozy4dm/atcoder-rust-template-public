// 必要な問題で src/main.rs にコピーして使う。
struct Dsu {
    parent_or_size: Vec<isize>,
}

impl Dsu {
    fn new(n: usize) -> Self {
        Self {
            parent_or_size: vec![-1; n],
        }
    }

    fn leader(&mut self, a: usize) -> usize {
        if self.parent_or_size[a] < 0 {
            return a;
        }
        let root = self.leader(self.parent_or_size[a] as usize);
        self.parent_or_size[a] = root as isize;
        root
    }

    fn merge(&mut self, a: usize, b: usize) -> bool {
        let mut x = self.leader(a);
        let mut y = self.leader(b);
        if x == y {
            return false;
        }
        if -self.parent_or_size[x] < -self.parent_or_size[y] {
            std::mem::swap(&mut x, &mut y);
        }
        self.parent_or_size[x] += self.parent_or_size[y];
        self.parent_or_size[y] = x as isize;
        true
    }

    fn same(&mut self, a: usize, b: usize) -> bool {
        self.leader(a) == self.leader(b)
    }

    fn size(&mut self, a: usize) -> usize {
        let root = self.leader(a);
        -self.parent_or_size[root] as usize
    }
}

#[cfg(test)]
mod tests {
    use super::Dsu;

    #[test]
    fn connected_components() {
        let mut dsu = Dsu::new(4);
        assert!(dsu.merge(0, 1));
        assert!(dsu.merge(1, 2));
        assert!(!dsu.merge(0, 2));
        assert!(dsu.same(0, 2));
        assert!(!dsu.same(0, 3));
        assert_eq!(dsu.size(1), 3);
    }
}
