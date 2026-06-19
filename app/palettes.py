PALETTES: dict[str, str | None] = {
    'Standard': '@%#*+=-:. ',
    'Extended': '$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,"^\'. ',
    'Block': '█▓▒░ ',
    'Braille': None,
    'Minimal': '@:. ',
    'Custom': None,
}


def get(name: str, custom: str = '') -> str | None:
    if name == 'Custom':
        return custom or '@. '
    if name == 'Braille':
        return None
    return PALETTES.get(name, PALETTES['Standard'])
