import sys, os
H = os.path.dirname(os.path.abspath(__file__)); F = os.path.join(H, '..', 'rsite', 'index.html')
s = open(F, encoding='utf-8').read()
a, b = s.index('// @@B06-START\n'), s.index('// @@B06-END\n')
mod = open(os.path.join(H, 'b06_module.js'), encoding='utf-8').read(); data = open(os.path.join(H, 'b06.json'), encoding='utf-8').read()
s = s[:a] + '// @@B06-START\nconst B6DATA = ' + data + ';\n' + mod + s[b:]
open(F, 'w', encoding='utf-8').write(s); print('injected', len(s))
