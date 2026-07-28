# 日本购物网站库存监控工作台（本地测试版）

监控网站：
- https://lifes-203.com/
- https://etretokyo.jp/shop/default.aspx

## 已实现
- 本地网页工作台
- SQLite 数据库
- 每 60 分钟执行一次全站扫描
- 手动“立即检查”
- 商品、颜色、尺码库存快照
- 有货→缺货、缺货→有货变化记录
- 商品/颜色/尺码级别的变化展示
- 两个网站独立监控器
- 失败不误判为缺货

## 重要说明
这是“测试版框架”。两个网站会调整页面结构，颜色/尺码库存通常由 JavaScript 动态生成。
因此首次运行后，请在工作台查看“原始解析结果”和“检查失败”信息，再根据实际页面调整
`app/monitors/lifes.py` 与 `app/monitors/etre.py` 中的选择器。

## Mac 安装运行

打开“终端”，进入项目目录：

```bash
cd ~/Downloads/jp_stock_monitor_test
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

浏览器打开：

http://127.0.0.1:8000

停止运行：回到终端按 `Control + C`

## Windows

```powershell
cd $HOME\Downloads\jp_stock_monitor_test
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

## 第一次测试建议

1. 启动工作台
2. 点击“立即检查”
3. 等待扫描完成
4. 打开“检查日志”
5. 查看两个网站分别抓到了多少商品
6. 随机打开几个商品详情页，核对颜色、尺码、库存状态
7. 第二次扫描后，系统才会开始可靠地产生“变化记录”

## 当前库存状态定义

- `in_stock`：可购买 / 有库存 / 残りわずか
- `out_of_stock`：SOLD OUT / 在庫切れ / 入荷待ち / 再入荷待ち
- `preorder`：预约、预售
- `coming_soon`：未发售
- `unknown`：无法确认，不会当作缺货

## 后续可加
- 企业微信机器人通知
- 登录保护
- 商品图片缓存
- 热门/重点商品自动评分
- 云端部署
