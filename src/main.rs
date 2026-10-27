// このコードは、以下のリポジトリで公開しているコード類を利用しています。
// https://github.com/ozy4dm/atcoder-rust-template-public
// itertools: 配列の組合せ・順列・連続要素のグループ化などを簡潔に書ける。
#[allow(unused_imports)]
use itertools::Itertools;
// either: 2種類の結果を Either::Left / Right でまとめて扱える。
#[allow(unused_imports)]
use either::Either;
// proconio: input! で数値・配列・文字列を型付きで読み取る。Usize1 は1始まりの番号を0始まりに直す。
#[allow(unused_imports)]
use proconio::{input, marker::{Chars, Usize1}};
// ac-library-rs: Dsu で連結成分を管理できる。セグメント木なども必要に応じて追加できる。
#[allow(unused_imports)]
use ac_library::Dsu;
// superslice: ソート済み配列の lower_bound / upper_bound で二分探索できる。
#[allow(unused_imports)]
use superslice::Ext;
// num-integer: gcd・lcm など整数の計算に使える。
#[allow(unused_imports)]
use num_integer::Integer;
// rustc-hash: FxHashMap / FxHashSet で高速なハッシュ表・集合を使える。
#[allow(unused_imports)]
use rustc_hash::{FxHashMap, FxHashSet};
// Reverse: BinaryHeap を小さい値から取り出す優先度付きキューにできる。
#[allow(unused_imports)]
use std::cmp::Reverse;
// 標準ライブラリ: 集合・辞書・キュー・優先度付きキューを必要に応じて使う。
#[allow(unused_imports)]
use std::collections::{BTreeMap, BTreeSet, BinaryHeap, HashMap, HashSet, VecDeque};

fn main() {
    // 入力形式に合わせて、必要な行だけ自分で有効にして書き換える。
    // input! {
    //     n: usize,
    //     a: [i64; n],
    // }
}
