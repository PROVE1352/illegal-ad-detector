# GUI 스모크 판정 자체 검증용: 한글 제목 창을 띄우고 mainloop 에 들어간다(스모크가 PASS 해야 정상).
import tkinter as tk

root = tk.Tk()
root.title("불법광고 탐지 셀프테스트")
tk.Label(root, text="한글 라벨 확인").pack(padx=20, pady=20)
root.mainloop()
