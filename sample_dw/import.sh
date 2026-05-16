#!/bin/bash
# 导入 mavenfuzzyfactory 示例数据到 Docker MySQL
# 用法: bash sample_dw/import.sh

set -e

SQL_FILE="sample_dw/create_mavenfuzzyfactory-201115-113526.sql"
DB="mavenfuzzyfactory"
MYSQL_USER="root"
MYSQL_PASS="hikari123"

if [ ! -f "$SQL_FILE" ]; then
    echo "找不到 SQL 文件: $SQL_FILE"
    exit 1
fi

echo "1/4 重建数据库..."
docker exec mysql mysql -u$MYSQL_USER -p$MYSQL_PASS -e "
    SET FOREIGN_KEY_CHECKS=0;
    DROP DATABASE IF EXISTS $DB;
    SET FOREIGN_KEY_CHECKS=1;
    CREATE DATABASE $DB CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
" 2>/dev/null

echo "2/4 导入表结构..."
head -112 "$SQL_FILE" | sed '9,10d' | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null

echo "3/4 导入小表数据 (products, orders, order_items, order_item_refunds, website_sessions)..."
# products
sed -n '1661128,1661142p' "$SQL_FILE" | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null
# orders
sed -n '1661143,1693464p' "$SQL_FILE" | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null
# order_items
sed -n '1693465,1733500p' "$SQL_FILE" | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null
# order_item_refunds
sed -n '1733501,$p' "$SQL_FILE" | grep -v '^SET' | grep -v '^COMMIT' | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null
# website_sessions
sed -n '113,472993p' "$SQL_FILE" | docker exec -i mysql mysql -u$MYSQL_USER -p$MYSQL_PASS $DB 2>/dev/null

echo "4/4 导入 website_pageviews (120万行，分批处理)..."
python3 -c "
chunk_size = 10000
with open('$SQL_FILE') as f:
    lines = f.readlines()

with open('/tmp/pageviews_chunked.sql', 'w') as out:
    out.write('SET FOREIGN_KEY_CHECKS=0;\nSET UNIQUE_CHECKS=0;\n')
    batch = []
    for line in lines[472993:1661127]:
        line = line.strip()
        if not line or line.startswith('SET') or line.startswith('--') or line.startswith('COMMIT'):
            continue
        row = line.rstrip(',').rstrip(';')
        if not row.startswith('('):
            continue
        batch.append(row)
        if len(batch) >= chunk_size:
            out.write('INSERT INTO website_pageviews VALUES\n')
            out.write(',\n'.join(batch) + ';\n')
            batch = []
    if batch:
        out.write('INSERT INTO website_pageviews VALUES\n')
        out.write(',\n'.join(batch) + ';\n')
    out.write('SET FOREIGN_KEY_CHECKS=1;\nSET UNIQUE_CHECKS=1;\n')
"
docker cp /tmp/pageviews_chunked.sql mysql:/tmp/pageviews_chunked.sql
docker exec mysql bash -c "mysql -u$MYSQL_USER -p$MYSQL_PASS $DB < /tmp/pageviews_chunked.sql" 2>/dev/null

echo "导入完成！授权 hikari 用户..."
docker exec mysql mysql -u$MYSQL_USER -p$MYSQL_PASS -e "GRANT ALL PRIVILEGES ON *.* TO 'hikari'@'%'; FLUSH PRIVILEGES;" 2>/dev/null

docker exec mysql mysql -u$MYSQL_USER -p$MYSQL_PASS -e "
    SELECT 'website_sessions' AS 表名, COUNT(*) AS 行数 FROM $DB.website_sessions
    UNION ALL SELECT 'website_pageviews', COUNT(*) FROM $DB.website_pageviews
    UNION ALL SELECT 'products', COUNT(*) FROM $DB.products
    UNION ALL SELECT 'orders', COUNT(*) FROM $DB.orders
    UNION ALL SELECT 'order_items', COUNT(*) FROM $DB.order_items
    UNION ALL SELECT 'order_item_refunds', COUNT(*) FROM $DB.order_item_refunds;
" 2>/dev/null
