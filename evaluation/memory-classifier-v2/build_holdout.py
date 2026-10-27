"""New author-labelled examples, frozen before the first comparison run."""

import json
from pathlib import Path

ROOT = Path(__file__).parent
GROUPS = {
    "working": [
        "刚才试穿的腰围是七十四，我换到另一排，还拿这个数和新裤子比着。",
        "语音里说了三个包裹的位置，我一边回想一边挨个找。",
        "算账算到一百二十了，我接着把运费加进去。",
        "老师刚拍了四下节奏，我先在心里跟一遍，再拍给他听。",
        "这局还剩两张牌没见过，我记着它们，正想该出哪张。",
        "桌上三杯饮料谁点的我刚问过，现在正一杯杯对着人递过去。",
        "刚才称过空盒是四十克，我拿总重减掉它，算里面东西多重。",
        "对方刚说了一个新邮箱，我来不及写，先在心里重复着。",
    ],
    "episodic": [
        "今天我把公交卡落家里了，只好走路去单位。",
        "那回爬到山顶，才发现相机一直没开机。",
        "昨晚我去接妹妹，站错了校门，等了好久。",
        "前天试着修水龙头，最后弄湿了半个厨房。",
        "上次回老家，我和表弟在院子里下了一下午棋。",
        "今早我刚进办公室，同事就递给我一块热烧饼。",
        "第一次参加合唱时，我紧张得唱快了一拍。",
        "昨天我在路口摔了一跤，路人帮我扶起了车。",
    ],
    "semantic": [
        "我外公以前是小学老师。",
        "我读初中的城市是厦门。",
        "我吃饺子喜欢蘸醋。",
        "这间活动室每逢月底周五打扫。",
        "换相机电池之前要关机，这个步骤我知道。",
        "我能说出煮米饭的步骤：淘米、加水，再按煮饭键。",
        "舅舅做葱油面，总是先把葱炸香再拌面。",
        "我能讲清平结怎么打：两根绳先交叉，再换方向打一个结。",
    ],
    "procedural": [
        "竹笛我学过，能连贯地吹完整首小曲。",
        "我练会了反手转笔，一只手就能转好几圈。",
        "钩针我会用，能钩出一个小杯垫。",
        "我会倒立，靠墙能自己撑起来。",
        "这套广播操我跟得上，动作都做得出来。",
        "溜冰我练了两年，能顺着弯道滑过去。",
        "我会打水漂，小石片能在水上连跳几下。",
        "我能用二胡把这段旋律拉顺，换弦也不会卡住。",
    ],
}


def main():
    cases = [
        {"id": f"H{i:03}", "memory_type": label, "example": example}
        for i, (label, example) in enumerate(
            (
                (label, example)
                for label, examples in GROUPS.items()
                for example in examples
            ),
            1,
        )
    ]
    assert len(cases) == len({c["example"] for c in cases}) == 32
    dataset = {
        "name": "新写的32条补充检查样本",
        "version": "holdout-authored-v1",
        "limitations": "在看过旧错例后按同一边界编写；首次调用前冻结，未经独立专家标注，不是外部盲测集。",
        "cases": cases,
    }
    (ROOT / "holdout.json").write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"
    )
    print("Wrote 32 new examples; no model calls.")


if __name__ == "__main__":
    main()
