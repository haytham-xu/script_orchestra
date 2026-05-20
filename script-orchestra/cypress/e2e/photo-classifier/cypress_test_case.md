## 测试大分类
* setting - 设置页面测试
* default group - 默认组页面测试（未分组文件）
* small group - 小组页面测试（已分组文件）
* batch select - 批量选择页面测试（从default group批量操作）
* group batch - 小组批量页面测试（从small group批量操作）

## 测试注意事项
* **文件系统验证**：所有文件移动操作后使用 `cy.verifyFileDistribution()` 命令验证文件分布（带重试机制），不要使用固定的 `cy.wait()` 等待文件系统同步
* **测试数据隔离**：
  - 每个测试使用独立的test_name创建独立目录
  - 每个测试前需调用 `cy.resetPhotoClassifierStore()` 清空Pinia store状态
  - `cy.loadTestMedia()` 会自动清理working state文件 (`.photo_classifier_working_state.json`)
* **按键操作特殊性**：Q/W键会自动调用 `nextFile()` 前进到下一张图片，测试中不要在Q/W键后再调用 `cy.goToNextImage()`，否则会造成跳跃（处理1,3,5,7而不是1,2,3,4）
* **边界情况**：空文件列表、单文件、第一个/最后一个位置
* **键盘快捷键**：Z=best, X=better, C=normal, Backspace=del, Enter=apply, 左右箭头=导航, Q=创建新组, W=添加到当前组
* **UI等待**：页面跳转后需等待.main-image可见 + 500ms Vue响应

---

## Setting 页面测试

### case 1: 修改root path并重新加载
* setup: 创建4个图片在测试目录A
* 操作：
  1. 进入photo-classifier主页
  2. 点击settings按钮打开设置抽屉
  3. 修改root path为测试目录A
  4. 点击"Save and Reload"
  5. 等待页面重新加载
* 验证：
  1. 验证settings抽屉显示的current path是测试目录A
  2. 验证主页显示的group card数量正确
  3. 验证能看到4个图片

### case 2: 切换root path清空working state
* setup:
  1. 创建测试目录A，包含4个图片
  2. 创建测试目录B，包含3个图片
  3. 在目录A中标记一些文件、创建group
* 操作：
  1. 从目录A切换到目录B（通过settings）
  2. 再切换回目录A
* 验证：
  1. 验证目录B加载时没有目录A的group
  2. 验证切换回目录A后，之前的标记和group都被清除（fresh start）

---

## Default Group 页面测试

### case 3: mark all normal并apply
* setup: 创建4个图片
* 操作：进入default group页面，点击mark all normal，apply（Enter键）
* 验证：验证原本的4个图片已经不在原目录，检查4个图片都进到了normal文件夹

### case 4: 混合标记（在第3张位置apply）
* setup: 创建4个图片
* 操作：进入default group页面，点击mark all normal，然后把第2张标记best（Z键），第3张标记better（X键），在第3张的位置apply（Enter键）
* 验证：验证原本的4个图片已经不在原目录，检查1,4在normal，2在best，3在better

### case 5: 混合标记（在第4张位置apply）
* setup: 创建4个图片
* 操作：进入default group页面，点击mark all normal，然后把第2张标记best（Z键），第3张标记better（X键），继续滑到第4张（右箭头），apply（Enter键）
* 验证：验证原本的4个图片已经不在原目录，检查1,4在normal，2在best，3在better

### case 6: 标记为del
* setup: 创建4个图片
* 操作：
  1. 进入default group页面
  2. 第1张标记normal（C键）
  3. 第2张标记del（Backspace键）
  4. 第3张标记normal（C键）
  5. 第4张标记del（Backspace键）
  6. Apply（Enter键）
* 验证：验证1,3在normal，2,4在del文件夹

### case 7: 创建新group（Q键）
* setup: 创建4个图片
* 操作：
  1. 进入default group页面
  2. 在第1张位置按Q键创建新group（Q键会自动前进到下一张）
  3. 再按Q键创建另一个新group（此时在第2张位置）
* 验证：
  1. 验证store中有2个group
  2. 验证group 0包含第1张图片
  3. 验证group 1包含第2张图片
  4. 验证图片的groupId正确
* 注意：Q键按下后会自动前进，不需要手动调用goToNextImage

### case 8: 添加到现有group（W键）
* setup: 创建4个图片
* 操作：
  1. 进入default group页面
  2. 在第1张按Q创建group 0（自动前进到第2张）
  3. 按W添加第2张到当前group（group 0）（自动前进到第3张）
  4. 按Q创建group 1（自动前进到第4张）
  5. 先选择group 1为current，然后按W添加第4张
* 验证：
  1. 验证group 0包含第1,2张
  2. 验证group 1包含第3,4张
* 注意：Q/W键按下后会自动前进，不需要手动调用goToNextImage

### case 9: 显示Group抽屉并添加文件
* setup: 创建6个图片
* 操作：
  1. 进入default group，创建2个group（Q键）
  2. 点击"显示Group"按钮打开抽屉
  3. 导航到第3张，点击抽屉中group 0的Add按钮
  4. 导航到第4张，点击group 1的Add按钮
* 验证：
  1. 验证抽屉显示2个group card
  2. 验证group 0有2张图片
  3. 验证group 1有2张图片

### case 10: 切换"未标识"过滤器
* setup: 创建6个图片
* 操作：
  1. 进入default group
  2. 第1,2张添加到group（Q键）
  3. 打开"未标识"开关
* 验证：
  1. 验证只显示4张未分组的图片（3,4,5,6）
  2. 验证index显示1/4而不是1/6

### case 11: 边界情况 - 空文件列表
* setup: 创建空测试目录（0个文件）
* 操作：进入default group页面
* 验证：
  1. 验证显示0/0
  2. 验证没有崩溃
  3. 验证mark all normal按钮可点击但无效果

### case 12: 边界情况 - 单文件
* setup: 创建1个图片
* 操作：
  1. 进入default group
  2. 标记为best（Z键）
  3. Apply（Enter键）
* 验证：
  1. 验证文件移动到best文件夹
  2. 验证remaining=0

### case 13: 左右导航边界
* setup: 创建3个图片
* 操作：
  1. 进入default group（默认在第1张）
  2. 按左箭头10次
  3. 按右箭头10次
* 验证：
  1. 验证在第1张时按左箭头不会越界（仍在index 0）
  2. 验证在最后一张时按右箭头不会越界（仍在index 2）

### case 14: 页面刷新/直接访问URL
* setup: 创建4个图片
* 操作：
  1. 直接访问URL: http://localhost:5173/photo-classifier/default-group
  2. 等待页面加载
* 验证：
  1. 验证页面正常显示4张图片（不是0/0）
  2. 验证数据正确初始化（测试direct URL access修复）

---

## Small Group 页面测试

### case 15: group页面标记并apply
* setup: 创建4个图片，全部添加到group 0
* 操作：
  1. 进入group 0页面（/photo-classifier/group/0）
  2. 点击mark all normal
  3. 第2张改为best（Z键）
  4. Apply（Enter键）
* 验证：
  1. 验证1,3,4在normal，2在best
  2. 验证apply后自动跳转到下一个group（如果有）或提示"Already the last group"

### case 16: 在group间导航
* setup:
  1. 创建6个图片
  2. 第1,2张添加到group 0
  3. 第3,4张添加到group 1
  4. 第5,6张添加到group 2
* 操作：
  1. 进入group 0
  2. 按快捷键或点击按钮导航到下一个group
  3. 在group 2尝试导航到下一个group
  4. 导航回到上一个group
  5. 在group 0尝试导航到上一个group
* 验证：
  1. 验证正确跳转到group 1
  2. 验证在最后一个group时显示提示"Already the last group"
  3. 验证正确返回到group 1
  4. 验证在第一个group时显示提示"Already the first group"

### case 17: group内左右导航
* setup: 创建3个图片，全部添加到group 0
* 操作：
  1. 进入group 0（默认第1张）
  2. 按右箭头到第2张
  3. 按右箭头到第3张
  4. 按右箭头（已在最后）
  5. 按左箭头返回
* 验证：
  1. 验证正确显示index: 1/3, 2/3, 3/3
  2. 验证在最后一张时按右箭头不会越界
  3. 验证在第一张时按左箭头不会越界

### case 18: group页面进入batch模式
* setup: 创建5个图片，全部添加到group 0
* 操作：
  1. 进入group 0
  2. 点击"批量操作"按钮
* 验证：
  1. 验证跳转到/photo-classifier/group/0/batch
  2. 验证显示5张图片的缩略图网格

### case 19: 空group边界情况
* setup:
  1. 创建2个图片
  2. 创建group 0但不添加任何文件（通过API或手动操作）
* 操作：进入group 0页面
* 验证：
  1. 验证显示0/0
  2. 验证mark all normal无效果
  3. 验证没有崩溃

---

## Batch Select 页面测试（从default group批量操作）

### case 20: 单选和取消选择
* setup: 创建6个图片
* 操作：
  1. 进入批量选择页面（/photo-classifier/batch-select）
  2. 点击第1张图片
  3. 点击第3张图片
  4. 再次点击第1张图片取消选择
* 验证：
  1. 验证选中状态正确显示（复选框图标）
  2. 验证选中计数正确：0 → 1 → 2 → 1

### case 21: Shift范围选择
* setup: 创建10个图片
* 操作：
  1. 进入批量选择页面
  2. 点击第2张
  3. 按住Shift点击第6张
* 验证：验证第2,3,4,5,6张都被选中（共5张）

### case 22: 创建新group（批量）
* setup: 创建8个图片
* 操作：
  1. 进入批量选择页面
  2. 选择第1,3,5张（点击）
  3. 点击"创建新分组"按钮
* 验证：
  1. 验证创建了新group
  2. 验证group包含3张图片
  3. 验证选择被清空
  4. 验证显示成功消息

### case 23: 添加到现有group（批量）
* setup:
  1. 创建8个图片
  2. 第1,2张已经在group 0
* 操作：
  1. 进入批量选择页面
  2. 选择第3,4,5张
  3. 点击"添加到已有分组"
  4. 在抽屉中选择group 0
* 验证：
  1. 验证group 0现在有5张图片
  2. 验证选择被清空
  3. 验证抽屉关闭

### case 24: 切换"仅显示未分组"过滤器
* setup:
  1. 创建10个图片
  2. 第1,2,3张添加到group 0
* 操作：
  1. 进入批量选择页面（显示全部10张）
  2. 打开"仅显示未分组"开关
  3. 选择2张图片
  4. 关闭"仅显示未分组"开关
* 验证：
  1. 验证开关打开后只显示7张未分组图片
  2. 验证切换过滤器时选择被清空
  3. 验证关闭开关后显示全部10张

### case 25: 清空选择
* setup: 创建6个图片
* 操作：
  1. 进入批量选择页面
  2. 选择3张图片
  3. 点击"清空选择"按钮
* 验证：验证所有选择被清除，计数显示0

### case 26: 未选择图片时的操作提示
* setup: 创建4个图片
* 操作：
  1. 进入批量选择页面（不选择任何图片）
  2. 点击"创建新分组"
  3. 点击"添加到已有分组"
* 验证：验证两次都显示警告消息"请先选择图片"

### case 27: 批量选择边界 - 全选
* setup: 创建5个图片
* 操作：
  1. 进入批量选择页面
  2. 点击第1张
  3. Shift+点击第5张（选中全部）
  4. 创建新group
* 验证：
  1. 验证5张全部被选中
  2. 验证新group包含5张
  3. 验证default group为空

### case 28: 无限滚动加载
* setup: 创建150个图片（超过pageSize=100）
* 操作：
  1. 进入批量选择页面
  2. 滚动到底部
  3. 等待加载更多
* 验证：
  1. 验证初始只加载100张
  2. 验证滚动后加载剩余50张
  3. 验证总共显示150张

---

## Group Batch 页面测试（从small group批量操作）

### case 29: 从group中批量移除
* setup: 创建6个图片，全部添加到group 0
* 操作：
  1. 进入group 0
  2. 进入batch模式（/photo-classifier/group/0/batch）
  3. 选择第1,3,5张
  4. 点击"从分组中移除"
  5. 确认对话框
* 验证：
  1. 验证group 0只剩3张（第2,4,6张）
  2. 验证被移除的文件回到default group
  3. 验证选择被清空

### case 30: 取消移除操作
* setup: 创建4个图片，全部添加到group 0
* 操作：
  1. 进入group batch模式
  2. 选择2张图片
  3. 点击"从分组中移除"
  4. 在确认对话框点击"取消"
* 验证：
  1. 验证group 0仍有4张图片
  2. 验证选择状态保持

### case 31: group batch中的Shift范围选择
* setup: 创建10个图片，全部添加到group 0
* 操作：
  1. 进入group batch模式
  2. 点击第3张
  3. Shift+点击第7张
* 验证：验证第3,4,5,6,7张被选中（共5张）

### case 32: group batch无限滚动
* setup: 创建150个图片，全部添加到group 0
* 操作：
  1. 进入group batch模式
  2. 滚动到底部触发加载
* 验证：
  1. 验证初始加载100张
  2. 验证滚动后加载剩余50张
  3. 验证共150张

### case 33: 空选择时的移除提示
* setup: 创建4个图片，全部添加到group 0
* 操作：
  1. 进入group batch模式（不选择任何图片）
  2. 点击"从分组中移除"
* 验证：验证显示警告"请先选择要移除的图片"

---

## 综合场景测试

### case 34: 完整workflow - 从导入到分类到应用
* setup: 创建10个图片
* 操作：
  1. 进入default group
  2. 使用Q/W键创建group 0，包含第1,2,3张（注意Q/W自动前进）
  3. 使用Q/W键创建group 1，包含第4,5张
  4. 第6张标记normal，第7张标记best，第8,9张标记del
  5. 第10张保持未处理
  6. 进入group 0，mark all better，apply
  7. 进入group 1，mark all best，apply
  8. 返回default group，apply剩余文件
* 验证：
  1. 使用 `cy.verifyFileDistribution()` 验证group 0的3张在better文件夹（001-003）
  2. 验证group 1的2张在best文件夹（004-005）
  3. 验证1张在normal（006），1张在best（007），2张在del（008-009）
  4. 验证第10张仍在原目录（remaining=1）
* 注意：此测试验证完整的文件分类和移动流程，需要正确处理Q/W键的自动前进行为

### case 35: working state保存和恢复
* setup: 创建6个图片
* 操作：
  1. 进入default group
  2. 创建group 0，添加2张
  3. 标记第3张为best（不apply）
  4. 刷新页面
* 验证：
  1. 验证刷新后group 0仍存在且有2张
  2. 验证第3张的best标记被保留
  3. 验证currentGroupIndex被恢复

### case 36: 清空working state
* setup: 创建6个图片，创建group并标记
* 操作：
  1. 在default group中apply所有文件
  2. 检查后端working state
* 验证：验证apply后working state被清除

### case 37: Reset功能
* setup:
  1. 创建10个图片
  2. 创建2个group
  3. 标记多个文件
* 操作：
  1. 在Dashboard点击"Reset"按钮
  2. 确认对话框
* 验证：
  1. 验证所有group被清除
  2. 验证所有categoryTag被清除
  3. 验证所有文件回到pending状态
  4. 验证显示成功消息

### case 38: 混合图片和视频
* setup: 创建3个图片和2个视频
* 操作：
  1. 进入default group
  2. 标记第1个文件（图片）为best
  3. 标记第3个文件（可能是视频）为normal
  4. 导航查看所有文件
  5. Apply
* 验证：
  1. 验证图片和视频都正确显示
  2. 验证MediaComponent正确识别文件类型
  3. 验证移动操作对图片和视频都有效

### case 39: 大量文件性能测试
* setup: 创建200个图片
* 操作：
  1. 进入default group（懒加载）
  2. 进入batch select（分页加载）
  3. 创建包含50张的group
  4. 进入group batch查看
* 验证：
  1. 验证页面不卡顿
  2. 验证滚动流畅
  3. 验证操作响应及时

### case 40: 跨页面导航流程
* setup: 创建6个图片
* 操作：
  1. Dashboard → Default Group
  2. 创建group → 打开Group抽屉 → 点击group avatar
  3. 进入Small Group → 点击batch按钮
  4. Group Batch → 返回 → Dashboard
  5. Dashboard → Batch Select → 返回
* 验证：
  1. 验证所有页面跳转正确
  2. 验证数据在页面间正确传递
  3. 验证返回按钮功能正常
  4. 验证没有内存泄漏或状态污染
