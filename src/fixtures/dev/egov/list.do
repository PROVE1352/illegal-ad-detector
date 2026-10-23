<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>전자정부 게시판 - 행복시청</title>
<style>
body{font-family:sans-serif;margin:0;background:#fff;color:#222}
.header{background:#0b4ea2;color:#fff;padding:14px 24px}
.nav a{color:#fff;margin-right:12px;text-decoration:none}
.container{max-width:960px;margin:0 auto;padding:16px}
table.board-list{width:100%;border-collapse:collapse}
table.board-list td,table.board-list th{border-bottom:1px solid #ddd;padding:8px}
.article-body{line-height:1.7}
.comments{margin-top:24px;border-top:2px solid #eee}
.comment{padding:8px 0;border-bottom:1px solid #eee}
.sr-only{position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden}
.footer{color:#666;font-size:12px;padding:16px;border-top:1px solid #ddd}
</style></head><body>
<div class="header"><h1>행복시청</h1><div class="nav"><a href="index.html">공지사항</a><a href="about.html">기관소개</a><a href="index.html">목록</a></div></div>
<div class="container"><form name="frm" method="post" action="view.do"><input type="hidden" name="nttId"><input type="hidden" name="bbsId" value="BBSMSTR_000000000006"></form><table class="board-list"><tr><td class="num">1</td><td class="title"><a href="#none" onclick="fn_egov_select_notice('1'); return false;">공지 1</a></td></tr><tr><td class="num">2</td><td class="title"><a href="#none" onclick="fn_egov_select_notice('2'); return false;">공지 2</a></td></tr><tr><td class="num">3</td><td class="title"><a href="#none" onclick="fn_egov_select_notice('3'); return false;">공지 3</a></td></tr><tr><td class="num">4</td><td class="title"><a href="#none" onclick="fn_egov_select_notice('4'); return false;">공지 4</a></td></tr><tr><td class="num">5</td><td class="title"><a href="#none" onclick="fn_egov_select_notice('5'); return false;">공지 5</a></td></tr></table><script>function fn_egov_select_notice(nttId) { document.frm.nttId.value = nttId; document.frm.action = "view.do"; document.frm.submit(); }</script></div>
<div class="footer">행복시청 · 행복로 1 · 전화 02-000-0000 · <a href="https://www.mois.go.kr">행정안전부</a></div>
</body></html>