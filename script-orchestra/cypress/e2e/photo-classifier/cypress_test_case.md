# Photo Classifier - Cypress E2E Test Cases (详细版)

## 📋 测试文件清单

| 文件名 | Case数量 | 描述 |
|-------|---------|------|
| 01-basic-media-loading.cy.ts | 5 | 基础媒体加载 (Case 1-5) |
| 02-file-categorization.cy.ts | 3 | 文件分类 (Case 8-10) |
| 03-default-group-operations.cy.ts | 9 | Default Group操作 (Case 11-19) |
| 04-small-group-operations.cy.ts | 5 | Small Group操作 (Case 15-19) |
| 05-batch-select.cy.ts | 9 | 批量选择 (Case 20-28) |
| 06-group-batch.cy.ts | 5 | Group批量操作 (Case 29-33) |
| 07-settings.cy.ts | 2 | 设置管理 (Case 6-7) |
| 08-integration.cy.ts | 7 | 综合场景 (Case 34-40) |
| 99-cleanup.cy.ts | 1 | 清理测试数据 |
| **总计** | **46** | **完整覆盖** |

**注**: 测试注意事项和最佳实践请参考 [Cypress Common Standards](../CYPRESS_STANDARDS.md)

---

## 01-basic-media-loading.cy.ts - 基础媒体加载测试

### Case 1: 创建图片并验证文件系统
**测试**: `should create test images and verify file system`

**测试流程**:
1. 在`/backend/cypress_test_data/photo_classifier`创建文件夹`test_images_only`
2. 在文件夹内创建3张前缀为`img`的图片
   - **预期**: 返回3个图片路径，0个视频路径
   - **预期**: 文件实际存在于文件系统
   - **预期**: 文件命名格式：`img_image_001.jpg`, `img_image_002.jpg`, `img_image_003.jpg`

---

### Case 2: 创建视频并验证文件系统
**测试**: `should create test videos and verify file system`

**测试流程**:
1. 在`/backend/cypress_test_data/photo_classifier`创建文件夹`test_videos_only`
2. 在文件夹内创建2个前缀为`vid`的视频
   - **预期**: 返回0个图片路径，2个视频路径
   - **预期**: 文件命名格式：`vid_video_001.mp4`, `vid_video_002.mp4`

---

### Case 3: 创建混合媒体并验证文件系统
**测试**: `should create mixed media`

**测试流程**:
1. 创建文件夹`test_mixed_media`
2. 在文件夹内创建2张图片和1个视频，前缀为`mixed`
   - **预期**: 返回2个图片路径，1个视频路径
   - **预期**: 总共3个媒体文件创建成功

---

### Case 4: 加载媒体到PhotoClassifier前端
**测试**: `should load images and videos into PhotoClassifier frontend`

**测试流程**:
1. 创建3张图片和1个视频
2. 将测试目录加载到PhotoClassifier
   - **预期**: 页面跳转到`/photo-classifier` (Dashboard)
   - **预期**: Group card元素可见
   - **预期**: Dashboard正常加载，没有错误

**验证位置**: Dashboard页面，检查`.group-card`元素

---

### Case 5: 导航到default group并显示图片
**测试**: `should navigate to default group and display images`

**测试流程**:
1. 创建4张图片并加载到PhotoClassifier
2. 点击default group card进入default group页面
   - **预期**: URL包含`/photo-classifier/default-group`
   - **预期**: Default group view可见
   - **预期**: 主图片显示
   - **预期**: Header显示`1 / 4`

**验证位置**: Default group页面，检查`.pc-default-group-view`和`.main-image`元素

---

## 02-file-categorization.cy.ts - 文件分类测试

### Case 8: Mark all normal并apply
**测试**: `should mark all files as normal and apply`

**测试流程**:
1. 创建4张图片并加载到default group
2. 等待主图片可见 + 500ms
3. 点击"Mark All Normal"按钮
   - **预期**: Header标签显示`normal`
4. 按Enter键apply
   - **预期**: 文件分布验证：normal=4, remaining=0
   - **预期**: 4个文件移动到`rootPath/normal/`文件夹
   - **预期**: 原目录不再有这4个文件

**注**: 关于文件系统验证的通用规则（maxRetries, retryDelay等）已记录在 [Cypress Common Standards](../CYPRESS_STANDARDS.md)

---

### Case 9: 混合标记（在第3张位置apply）
**测试**: `should mark files with different categories and apply at 3rd position`

**测试流程**:
1. 创建4张图片并进入default group
2. 点击"Mark All Normal"按钮（所有文件标记为normal）
3. 按右箭头到第2张，按Z键标记为best
4. 按右箭头到第3张，按X键标记为better
5. 在第3张位置按Enter键apply
   - **预期**: 文件分布验证：normal=2, best=1, better=1, remaining=0
   - **预期**: 文件1和4在normal文件夹
   - **预期**: 文件2在best文件夹
   - **预期**: 文件3在better文件夹

**关键点**: Apply可以在任意位置执行，不影响最终文件分布结果

---

### Case 10: 混合标记（在第4张位置apply）
**测试**: `should mark files with different categories and apply at 4th position`

**测试流程**:
1. 创建4张图片并进入default group
2. Mark all normal
3. 第2张标记为best，第3张标记为better
4. 导航到第4张
5. 在第4张位置apply
   - **预期**: 与Case 9相同：normal=2, best=1, better=1
   - **预期**: 验证apply位置不影响结果

---

## 03-default-group-operations.cy.ts - Default Group操作

### Case 11: 标记为del
**测试**: `should mark files as del and verify deletion`

**测试流程**:
1. 创建4张图片并进入default group
2. 标记模式：第1张=normal, 第2张=del, 第3张=normal, 第4张=del
3. Apply
   - **预期**: 文件分布：normal=2, del=2, remaining=0
   - **预期**: 文件1和3在normal文件夹
   - **预期**: 文件2和4在del文件夹

---

### Case 12: 创建新group（Q键）
**测试**: `should create new groups using Q key`

**测试流程**:
1. 创建4张图片并进入default group
2. 在第1张按Q创建group 0（Q键会自动前进到第2张）
3. 按右箭头到第3张，按Q创建group 1（Q键会自动前进到第4张）
4. 返回Dashboard
   - **预期**: Dashboard显示3个group card（1个default + 2个custom）
5. 点击group 0 card
   - **预期**: 显示`1 / 1`（只有文件1）
6. 点击group 1 card
   - **预期**: 显示`1 / 1`（只有文件2）
   - **预期**: Q键自动advance功能正常

**关键点**: Q键按下后会自动调用nextFile()前进，不要在Q键后再调用goToNextImage()

---

### Case 13: 添加到现有group（W键）
**测试**: `should add files to existing group using W key`

**测试流程**:
1. 创建4张图片并进入default group
2. 在第1张按Q创建group 0（自动到第2张）
3. 在第2张按W添加到group 0（自动到第3张）
4. 在第3张按Q创建group 1（自动到第4张）
5. 在第4张按W添加到group 1
6. 返回Dashboard
   - **预期**: Dashboard显示3个group card
7. 进入Group 0
   - **预期**: 显示`1 / 2`（文件1和2）
8. 进入Group 1
   - **预期**: 显示`1 / 2`（文件3和4）
   - **预期**: W键添加到当前选中group功能正常

---

### Case 14: 显示Group抽屉并添加文件
**测试**: `should use group drawer to add files to groups`

**测试流程**:
1. 创建6张图片并进入default group
2. 按Q创建group 0（文件1），等待300ms
3. 按Q创建group 1（文件2），等待300ms
4. 点击"显示Group"按钮打开抽屉
   - **预期**: 抽屉显示2个group avatar
5. 按右箭头到第3张，点击抽屉中group 0的Add按钮
6. 按右箭头到第4张，点击抽屉中group 1的Add按钮
   - **预期**: Group 0 avatar显示"2 files"
   - **预期**: Group 1 avatar显示"2 files"
7. 返回Dashboard
   - **预期**: 验证group card数量为3个（包含1个default group + 2个custom group）

**补充验证**: 在分组后，直接访问`/photo-classifier/group/0`或`/photo-classifier/group/1`，可以正确加载分组数据

---

### Case 15: 切换"未标识"过滤器
**测试**: `should filter unidentified files correctly`

**测试流程**:
1. 创建6张图片并进入default group
2. 在第1张按Q创建group（自动到第2张）
3. 在第2张按W添加到group（自动到第3张）
4. 在第3张按W添加到group（自动到第4张）
5. 验证显示`4 / 6`（3个文件已分组，当前在第4个）
6. 点击"未标识"过滤器开关
7. 等待500ms
   - **预期**: 显示从`4 / 6`变为`1 / 3`
   - **预期**: 只显示未分组的3个文件（文件4, 5, 6）
8. 按右箭头验证
   - **预期**: 显示`2 / 3`、`3 / 3`
9. 切换回过滤器（关闭"未标识"开关）
   - **预期**: 显示恢复为`6 / 6`（当前位置在文件6）

---

### Case 16: 边界情况 - 空文件列表
**测试**: `should handle empty file list gracefully`

**测试流程**:
1. 创建空测试目录（0个文件）
2. 加载空目录
3. 直接访问URL `/photo-classifier/default-group`
4. 点击"Mark All Normal"按钮
   - **预期**: 显示`0 / 0`
   - **预期**: Mark All Normal按钮点击无报错
   - **预期**: 页面不崩溃，不显示错误

---

### Case 17: 边界情况 - 单文件
**测试**: `should handle single file correctly`

**测试流程**:
1. 创建1张图片
2. 进入default group
   - **预期**: 显示`1 / 1`
3. 按Z键标记为best
4. 按Enter键apply
   - **预期**: 文件分布验证：best=1, remaining=0
   - **预期**: 文件移动到best文件夹
   - **预期**: 单文件场景处理正常

---

### Case 18: 左右导航边界
**测试**: `should respect navigation boundaries`

**测试流程**:
1. 创建3张图片并进入default group
2. 默认在第1张（`1 / 3`）
3. 按左箭头10次
   - **预期**: 仍显示`1 / 3`
   - **预期**: 在第1张时按左箭头保持在第1张（不越界）
4. 按右箭头2次到第3张（`3 / 3`）
5. 按右箭头10次
   - **预期**: 仍显示`3 / 3`
   - **预期**: 在最后一张时按右箭头保持在最后一张（不越界）
   - **预期**: 没有循环导航

---

### Case 19: 页面刷新/直接访问URL
**测试**: `should handle direct URL access correctly`

**测试流程**:
1. 创建4张图片并加载
2. 直接访问URL: `http://localhost:5173/photo-classifier/default-group`
3. 等待主图片元素加载（timeout 10秒）
   - **预期**: 页面正常显示`1 / 4`（不是`0 / 0`）
   - **预期**: 主图片可见
4. 按右箭头导航到第2张
   - **预期**: 显示`2 / 4`
   - **预期**: 直接URL访问不会导致数据初始化失败

---

## 04-small-group-operations.cy.ts - Small Group操作

### Case 15: Group内标记并apply
**测试**: `should mark files in group and apply successfully`

**测试流程**:
1. 创建4张图片并进入default group
2. 等待主图片可见 + 500ms
3. 将所有4个文件添加到group 0（按Q创建，然后按3次W添加）
   - **预期**: Q键和W键都会自动前进
4. 访问`/photo-classifier/group/0`
5. 等待主图片可见 + 500ms
6. 点击"Mark All Normal"按钮
   - **预期**: 所有4个文件标记为normal
7. 按右箭头到第2张，按Z键标记为best（覆盖normal）
8. 按Enter键apply
   - **预期**: 文件分布验证：normal=3, best=1, remaining=0
   - **预期**: 文件正确移动到对应文件夹

---

### Case 16: 在groups之间导航
**测试**: `should navigate between groups correctly`

**测试流程**:
1. 创建6张图片并进入default group
2. 创建3个group，每个包含2个文件
   - Group 0: 文件1,2
   - Group 1: 文件3,4
   - Group 2: 文件5,6
3. 访问`/photo-classifier/group/0`
   - **预期**: URL包含`/group/0`
   - **预期**: 主图片可见
4. 点击"下一组"按钮
   - **预期**: URL变为`/group/1`
5. 再次点击"下一组"按钮
   - **预期**: URL变为`/group/2`
6. 在最后一组时点击"下一组"按钮
   - **预期**: 保持在`/group/2`（不越界）
7. 点击"上一组"按钮
   - **预期**: URL变为`/group/1`
8. 访问`/photo-classifier/group/0`，点击"上一组"按钮
   - **预期**: 保持在`/group/0`（不越界）

---

### Case 17: Group内部导航
**测试**: `should navigate within group correctly`

**测试流程**:
1. 创建3张图片并进入default group
2. 将所有3个文件添加到group 0
3. 访问`/photo-classifier/group/0`
4. 等待主图片可见 + 1500ms
   - **预期**: 显示`1 / 3`
5. 按右箭头
   - **预期**: 显示`2 / 3`
6. 按右箭头
   - **预期**: 显示`3 / 3`
7. 再按右箭头（边界测试）
   - **预期**: 保持显示`3 / 3`（不越界）
8. 按左箭头
   - **预期**: 显示`2 / 3`

---

### Case 18: 从group进入batch模式
**测试**: `should enter batch mode from group view`

**测试流程**:
1. 创建5张图片并进入default group
2. 将所有5个文件添加到group 0
3. 访问`/photo-classifier/group/0`
4. 等待主图片可见 + 1000ms
5. 点击"批量管理"按钮
   - **预期**: URL包含`/group/0/batch`
   - **预期**: 显示图片网格
   - **预期**: 显示5个image card

---

### Case 19: 空group边界情况
**测试**: `should handle empty group gracefully`

**测试流程**:
1. 创建2张图片并进入default group
2. 按Q创建group 0（只包含文件1）
3. 访问不存在的group 1: `/photo-classifier/group/1`
   - **预期**: 页面不崩溃
   - **预期**: 能够正常处理空group或不存在的group（显示0/0或重定向）

---

## 05-batch-select.cy.ts - 批量选择操作

### Case 20: 单选和取消选择
**测试**: `should select and deselect files individually`

**测试流程**:
1. 创建6张图片并加载
2. 点击"批量选择"按钮进入batch select页面
3. 选择第1个文件（index 0）
   - **预期**: 选择计数显示1
4. 选择第3个文件（index 2）
   - **预期**: 选择计数显示2
5. 再次点击第1个文件取消选择
   - **预期**: 选择计数显示1

---

### Case 21: Shift范围选择
**测试**: `should select range of files with Shift`

**测试流程**:
1. 创建10张图片并加载
2. 进入batch select页面
3. 使用Shift选择index 1到5的范围（文件2-6，共5个文件）
   - **预期**: 选择计数显示5

---

### Case 22: 创建新group（批量）
**测试**: `should create new group with selected files`

**测试流程**:
1. 创建8张图片并加载
2. 进入batch select页面
3. 选择文件1, 3, 5（indices 0, 2, 4）
   - **预期**: 选择计数显示3
4. 点击"创建新分组"按钮
   - **预期**: 显示成功消息
   - **预期**: 选择被清除（计数为0）
5. 返回Dashboard
   - **预期**: 显示2个group card（1个default + 1个custom）

---

### Case 23: 添加到现有group（批量）
**测试**: `should add selected files to existing group`

**测试流程**:
1. 创建8张图片并加载
2. 进入default group，按Q创建group 0（文件1），按W添加文件2
3. 返回Dashboard，进入batch select页面
4. 选择文件3, 4, 5（indices 2, 3, 4）
   - **预期**: 选择计数显示3
5. 点击"添加到分组"按钮
   - **预期**: 抽屉打开显示group列表
6. 点击抽屉中group 0
   - **预期**: 抽屉关闭，选择被清除
7. 访问`/photo-classifier/group/0`
   - **预期**: 显示`1 / 5`（group 0现在有5个文件）

---

### Case 24: 切换"仅未分组"过滤器
**测试**: `should filter ungrouped files correctly`

**测试流程**:
1. 创建10张图片并加载
2. 进入default group，将前3个文件添加到group 0
3. 返回并进入batch select页面
   - **预期**: 显示所有10个image card
4. 点击"仅未分组"过滤器开关
   - **预期**: 只显示7个image card（未分组的文件）
5. 选择2个文件
   - **预期**: 选择计数显示2
6. 再次点击过滤器开关（关闭过滤）
   - **预期**: 显示所有10个image card
   - **预期**: 选择被清除（计数为0）

---

### Case 25: 清除选择
**测试**: `should clear selection when button clicked`

**测试流程**:
1. 创建6张图片并加载
2. 进入batch select页面
3. 选择3个文件（indices 0, 1, 2）
   - **预期**: 选择计数显示3
4. 点击"清除选择"按钮
   - **预期**: 选择计数变为0

---

### Case 26: 无选择时的警告
**测试**: `should show warning when no files selected`

**测试流程**:
1. 创建4张图片并加载
2. 进入batch select页面
3. 不选择任何文件
   - **预期**: "创建新分组"按钮处于禁用状态
   - **预期**: "添加到分组"按钮处于禁用状态

---

### Case 27: 选择所有文件
**测试**: `should select all files with shift range`

**测试流程**:
1. 创建5张图片并加载
2. 进入batch select页面
3. 使用Shift选择从index 0到4的范围（所有文件）
   - **预期**: 选择计数显示5
4. 点击"创建新分组"按钮
5. 返回Dashboard
   - **预期**: 显示2个group card（1个default + 1个custom）

---

### Case 28: 无限滚动加载
**测试**: `should load more files on scroll`

**测试流程**:
1. 创建150张图片并加载
2. 进入batch select页面
   - **预期**: 初始显示100个image card（pageSize）
3. 滚动到底部
4. 等待1000ms
   - **预期**: 加载更多文件，显示全部150个image card

---

## 06-group-batch.cy.ts - Group批量操作

### Case 29: 批量从group中移除
**测试**: `should remove selected files from group`

**测试流程**:
1. 创建6张图片并加载
2. 进入default group，将所有6个文件添加到group 0
3. 访问`/photo-classifier/group/0/batch`
4. 等待2000ms，图片网格可见
   - **预期**: 显示6个image card
5. 选择index 0, 2, 4的文件（文件1, 3, 5）
   - **预期**: 选择计数显示3
6. 点击"移除选中"按钮
7. 在确认对话框中点击确认
   - **预期**: 只剩3个image card
8. 访问`/photo-classifier/group/0`
   - **预期**: 显示`1 / 3`（只剩3个文件）

---

### Case 30: 取消移除操作
**测试**: `should cancel remove operation when user clicks cancel`

**测试流程**:
1. 创建4张图片并加载
2. 进入default group，将所有4个文件添加到group 0
3. 访问`/photo-classifier/group/0/batch`
4. 选择2个文件（indices 0, 1）
   - **预期**: 选择计数显示2
5. 点击"移除选中"按钮
6. 在确认对话框中点击取消
   - **预期**: 仍显示4个image card（未移除）
   - **预期**: 选择保持不变（计数仍为2）

---

### Case 31: Group batch中的Shift范围选择
**测试**: `should select range with shift in group batch`

**测试流程**:
1. 创建10张图片并加载
2. 进入default group，将所有10个文件添加到group 0
3. 访问`/photo-classifier/group/0/batch`
4. 使用Shift选择index 2到6的范围（5个文件）
   - **预期**: 选择计数显示5

---

### Case 32: Group batch中的无限滚动
**测试**: `should load more files on scroll in group batch`

**测试流程**:
1. 创建150张图片并加载
2. 进入batch select页面
3. 选择前100个文件（indices 0-99），点击"创建新分组"创建group 0
   - **此时group 0有100个文件**
4. 切换到"仅未分组"过滤器
   - **预期**: 显示剩余50个未分组文件
5. 选择这50个文件，点击"添加到分组"，选择group 0
   - **此时group 0共有150个文件**
6. 访问`/photo-classifier/group/0/batch`
   - **预期**: 初始显示100个image card（分页大小）
7. 滚动到底部
8. 等待1000ms
   - **预期**: 加载更多，显示超过100个image card（最终显示全部150个）



---

### Case 33: Group batch无选择时的警告
**测试**: `should show warning when removing without selection`

**测试流程**:
1. 创建4张图片并加载
2. 进入default group，将所有4个文件添加到group 0
3. 访问`/photo-classifier/group/0/batch`
4. 不选择任何文件
   - **预期**: "移除选中"按钮处于禁用状态

---

## 07-settings.cy.ts - 设置管理测试

### Case 6: 修改root path并重新加载
**测试**: `should modify root path and reload`

**测试流程**:
1. 创建测试目录A，包含4张图片
2. 进入photo-classifier主页（`/photo-classifier`）
3. 点击settings图标打开设置抽屉
4. 在textarea中输入测试目录A的完整路径
5. 点击"Save and Reload"按钮
6. 等待2秒页面自动reload
   - **预期**: 页面重新加载到`/photo-classifier`（Dashboard）
7. 重新打开settings抽屉
   - **预期**: current path显示为测试目录A
8. 验证Dashboard
   - **预期**: 显示group card（数据已加载）
9. 进入default group
   - **预期**: 显示`1 / 4`（4张图片）

---

### Case 7: 切换root path清空working state
**测试**: `should clear working state when switching root path`

**测试流程**:
1. 创建测试目录A（4张图片）和测试目录B（3张图片）
2. 通过API设置rootPath为目录A，访问Dashboard
3. 进入default group，按Q创建group 0
4. 按右箭头到第2张，按Z标记为best
5. 通过settings切换到目录B，等待reload
   - **预期**: group card只有1个（default group），无自定义group
6. 通过settings切换回目录A
   - **预期**: group card只有1个，之前创建的group 0被清除
7. 进入default group
   - **预期**: header不显示`best`标签（marks被清除）
   - **预期**: working state文件被清除（fresh start）

**关键点**:
- 加载测试媒体时会自动清理`.photo_classifier_working_state.json`
- 切换rootPath会触发working state清理
- 每个rootPath有独立的working state

---

## 08-integration.cy.ts - 综合场景测试

### Case 34: 完整workflow - 从导入到分类到应用
**测试**: `complete workflow from import to apply`

**测试流程**:
1. 创建10张图片，加载到default group
2. **创建Group 0（文件1, 2, 3）**:
   - 在第1张按Q创建group 0（自动到第2张）
   - 按W添加到group 0（自动到第3张）
   - 按W添加到group 0（自动到第4张）
3. **创建Group 1（文件4, 5）**:
   - 在第4张按Q创建group 1（自动到第5张）
   - 按W添加到group 1（自动到第6张）
4. **处理Group 0但不apply**:
   - 访问`/photo-classifier/group/0`
   - Mark all normal（文件1, 2, 3都标记normal）
   - 按右箭头到文件2，按X键标记better（覆盖normal）
   - **不要按Enter apply**
5. **处理Group 1但不apply**:
   - 访问`/photo-classifier/group/1`
   - Mark all normal（文件4, 5都标记normal）
   - **不要按Enter apply**
6. **处理default group剩余文件**:
   - 访问`/photo-classifier/default-group`
   - 点击"未分组only"过滤器，等待300ms
   - 验证显示`1 / 5`（文件6-10未分组）
   - 当前在文件6，按C键标记normal
   - 按右箭头到文件7，按Z键标记best
   - 按右箭头到文件8，按Backspace键标记del
   - 按右箭头到文件9，按Backspace键标记del
   - 按右箭头到文件10，不标记（保持unprocessed）
7. **一次性Apply所有文件**:
   - 按Enter键apply（会应用所有group和default group的marks）
   - **预期**: 文件分布：normal=5（文件1,3,4,5,6）, better=1（文件2）, best=1（文件7）, del=2（文件8,9）, remaining=1（文件10）
   - **预期**: 文件正确移动到对应文件夹（maxRetries=40, retryDelay=2000ms）

**关键点**: 测试"延迟apply"功能 - 在groups中标记但不立即apply，最后在default group一次性apply所有文件

---

### Case 35: working state保存和恢复
**测试**: `working state save and restore`

**测试流程**:
1. 创建6张图片并加载到default group
2. **创建group并标记但不apply**:
   - 在第1张按Q创建group 0（自动到第2张）
   - 在第2张按W添加到group 0（自动到第3张）
   - 在第3张按Z键标记为best
   - 等待500ms（确保autoSaveWorkingState执行）
3. **刷新页面测试持久化**:
   - 刷新页面（cy.reload()）
   - 等待1000ms让页面reload完成
4. **验证working state恢复**:
   - 访问`/photo-classifier` Dashboard
   - **预期**: group card有2个（1个default + 1个group 0）
5. 点击group 0的card（第2个card）
   - **预期**: URL变为`/photo-classifier/group/0`
   - **预期**: header显示`1 / 2`（group有2个文件）
6. **验证categoryTag恢复**:
   - 返回`/photo-classifier/default-group`
   - 点击"未分组only"过滤器
   - 等待500ms
   - **预期**: header包含`best`文本（文件3的标记被保留）

**关键点**:
- 测试autoSaveWorkingState和loadWorkingStateFromBackend功能
- Working state保存在`rootPath/.photo_classifier_working_state.json`

---

### Case 36: Apply后清空working state
**测试**: `should clear working state after applying files`

**测试流程**:
1. 创建6张图片并加载到default group
2. 按Q创建group 0（文件1）
3. 按右箭头到下一张，按Z标记为best（文件2）
4. 按Enter apply所有文件
5. 等待1000ms
   - **预期**: Working state被清空
   - **预期**: 重新加载后，之前的state不再恢复（fresh start）
   - **预期**: 文件分布验证：best=1（文件2），remaining=5（文件1在group中但未apply标签，文件3-6未处理）

**注**: 当前测试实现未包含文件系统验证，建议添加`cy.verifyFileDistribution()`

---

### Case 37: 重置功能
**测试**: `should reset all groups and marks`

**测试流程**:
1. 创建10张图片并加载到default group
2. 创建2个group（group 0和group 1）
3. 标记一些文件（best, normal等）
4. 返回Dashboard，点击"重置"按钮
5. 在确认对话框中点击确认
6. 等待1000ms
   - **预期**: 只剩1个group card（default group）
7. 进入default group
   - **预期**: header不显示任何标签（best, normal等）
   - **预期**: 所有分组和标记都被清除

---

### Case 38: 混合图片和视频
**测试**: `should handle mixed images and videos correctly`

**测试流程**:
1. 创建3张图片和2个视频（前缀'media'）
2. 通过API获取文件列表，识别第一个图片和第一个视频的index
   - **预期**: 文件列表中至少包含1个图片和1个视频
3. 加载到default group
   - **预期**: 显示`1 / 5`（共5个媒体文件）
4. 导航到第一个图片的位置，标记为best
5. 导航到第一个视频的位置，标记为normal
6. 按Enter apply
   - **预期**: 文件分布：best=1（图片），normal=1（视频），remaining=3
   - **预期**: 确保best和normal分别包含图片和视频类型

---

### Case 39: 大数据集性能测试
**测试**: `should handle large dataset without performance issues`

**测试流程**:
1. 创建200张图片并加载
2. 访问default group
   - **预期**: 主图片可见，显示`1 / 200`
3. 连续按右箭头3次快速导航
   - **预期**: 导航流畅无卡顿
4. 返回Dashboard，进入batch select
   - **预期**: 显示前100个image card（分页加载）
5. 使用Shift选择前50个文件，创建新group
6. 访问`/photo-classifier/group/0/batch`
   - **预期**: 显示50个image card，无性能问题

---

### Case 40: 跨页面导航流程
**测试**: `should navigate smoothly across all pages`

**测试流程**:
1. 创建6张图片并加载
   - **预期**: URL包含`/photo-classifier`（Dashboard）
2. 点击进入Default Group
   - **预期**: 主图片可见
3. 按Q创建group 0，按右箭头，按W添加第2个文件
4. 打开Group抽屉，点击group 0 avatar
   - **预期**: URL包含`/group/`（Small Group）
5. 点击"批量管理"按钮
   - **预期**: URL包含`/batch`（Group Batch）
6. 点击"返回"按钮
   - **预期**: URL包含`/photo-classifier`（Dashboard）
7. 点击"批量选择"按钮
   - **预期**: URL包含`/batch-select`（Batch Select）
8. 点击"返回"按钮
   - **预期**: URL包含`/photo-classifier`（Dashboard）
   - **预期**: 所有页面导航流畅无错误

---

## 99-cleanup.cy.ts - 清理测试数据

### 清理测试
**测试**: `should restore config and cleanup all test data`

**测试流程**:
1. 恢复配置快照（调用`cy.disableTestMode('photo_classifier')`）
   - **预期**: 配置恢复到测试前的原始状态
2. 清理所有测试数据（调用`cy.cleanupTest()`）
   - **预期**: 删除`/backend/cypress_test_data/photo_classifier`下的所有测试文件
   - **预期**: 清理完成，无测试数据残留

**关键点**:
- 使用`99-`前缀确保在所有测试最后执行（按字母顺序）
- 手动测试时（cypress open）可以跳过此测试，保留数据用于检查
- 自动化测试时（cypress run / CI）此测试会自动运行确保环境干净

---

**文档版本**: v4.0 (完整版)
**最后更新**: 2026-05-27
**状态**: ✅ 包含全部46个测试case + 清理说明

**注**: 测试注意事项和最佳实践已移至 [Cypress Common Standards](../CYPRESS_STANDARDS.md)
