"""旧多材料覆盖入口已停用，改用src.submission生成独立候选稿。"""

def build_materials(root, screenshot=None):
    raise ValueError('旧入口会覆盖多份材料，已停用。请使用 python -m src.submission --output build/新版本；详见docs/材料重建与交付.md。')


def main():
    import sys
    print('旧材料生成入口已停用。请使用 python -m src.submission --output build/新版本；不会改写docs。', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
