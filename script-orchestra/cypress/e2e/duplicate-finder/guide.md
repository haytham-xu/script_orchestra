
## Duplicate Finder
#### Test Case
整个测试都应该只在一个文件duplicate-finder.cy.ts

1. setting: 
    阅读现在Setting部分的代码实现，充分理解现有实现。
    备份Setting; 记录原本的值。
    打开设置页面，修改现有的所有设置的值，保存，重新打开(刷新页面)，检查所有测试值都被正确修改和保存了；
    恢复Setting，重新打开(刷新页面)
    使用之前保存的原始的Setting，检查值被正确的恢复了
2. phase flow happly path: 
    备份Setting; 设置成测试Setting(调大delay时间，调小间隔，测试数据库，del路径); 生成测试数据；至少包含120个duplicate group;
    触发phase1， 确认进度条条会发生变化，最后生成report，且report正确，
    触发phase2，确认进度条条会发生变化，最后生成report，且report正确，
    触发phase3，获得duplicate结果，获得的duplicate符合预期。检查只获取了前20个group的图片，而不是调用了所有API
    调整每组50个group，UI正确加载50个组
    跳转第二页，正确加载第二页
    清空测试数据，恢复Setting
    todo: 测试需要覆盖ignore to_del和igonre文件
3. delete one
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有1张图片f1i1.png, folder 2下有1张图片f2i1.png, f1i1.png,f2i1.png重复, 按照排序规则，其应该位于第一个group
    适当生成其他测试数据； 执行phase1，phase2,phase3
    获取group1，针对两张图片
        检查显示的路径是去掉folder path的相对路径
        检查点击Open Folder，确保功能正常
        选中f1i1.png，触发删除，
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
        f1i1.png应该被正确移动到了to_del/folder1/f1i1.png，
        scan_folder/folder1文件夹应该消失了
    清空测试数据，恢复Setting
3. delete all
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有2张图片f1i1.png, f1i2.png, folder2下有1张图片f2i1.png, f1i1.png,f2i1.png重复, 按照排序规则，其应该位于第一个group
    适当生成其他测试数据；执行phase1，phase2,phase3
    获取group1, 选择select all, 触发删除
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
        scan_folder/folder1还在，只剩下了f1i2.png
        scan_folder/folder2应该消失了
        to_del/folder1/f1i1.png存在
        to_del/folder2/f2i1.png存在
    清空测试数据，恢复Setting
4. deep delete - 1
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有10张图片, folder2下有10张图片, 他们刚好是10组group
    适当生成其他测试数据；执行phase1，phase2,phase3
    在deep delete表单中，填入folder1的路径，点击delete
        应该生成一个弹窗，弹窗列出了10张图片的列表(相对路径)
        点击确认删除
        scan_folder/folder1消失
        scan_folder/folder2还在
        to_del/folder1出现，有10张图片
        to_del/folder2不存在
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
    清空测试数据，恢复Setting
5. deep delete - 2
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有11张图片, folder2下有11张图片, 他们只有前10张图片互相重复，形成10个group
    适当生成其他测试数据；执行phase1，phase2,phase3
    在deep delete表单中，填入folder1的路径，点击delete
        应该生成一个弹窗，弹窗列出了10张图片的列表(相对路径)
        点击确认删除
        scan_folder/folder1还在，只有一张图片
        scan_folder/folder2还在，11张图片
        to_del/folder1出现，有10张图片
        to_del/folder2不存在
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
    清空测试数据，恢复Setting
6. deep delete - 3
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有10张图片, folder2下有10张图片, 他们刚好是10组group，按照排序规则，其应该位于前10个group
    适当生成其他测试数据；执行phase1，phase2,phase3
    点击group1里，folder1的那张图片的deep delete按钮，点击后
        应该生成一个弹窗，弹窗列出了10张图片的列表(相对路径)
        点击确认删除
        scan_folder/folder1消失
        scan_folder/folder2还在
        to_del/folder1出现，有10张图片
        to_del/folder2不存在
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
    清空测试数据，恢复Setting
7. white list
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有1张图片f1i1.png, folder 2下有1张图片f2i1.png, f1i1.png,f2i1.png重复, 按照排序规则，其应该位于第一个group
    适当生成其他测试数据； 执行phase1，phase2,phase3
    获取group1，点击Add to WhiteList
        该group应该从UI上消失了，
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
        UI应该重新加载了一个新的组，还是20个
        打开Setting页面，找到whitelist的部分，点击refresh按钮，该组应该出现在了whitelist列表里
        在Setting页面，将该组从whitelist列表移除
        关闭Setting页面
        在duplicate report里，duplicate group和duplicate文件数量等应该正确更新了
        UI应该重新加载了，还是20个，且回来的组依然在最顶部
    清空测试数据，恢复Setting
8. 复杂场景 - 1
    备份Setting; 设置成测试Setting(测试数据库，del路径); 
    生成测试数据；folder1下有10张图片, folder2下有10张图片, folder3下面有10张图片，他们刚好是10组group，按照排序规则，其应该位于前10个group
    适当生成其他测试数据；执行phase1，phase2,phase3
    group1，添加到whitelist
    group2, 添加到whitelist
    打开Setting页面，找到whitelist的部分，点击refresh按钮
        此时应该有2个组，每个组是3张图片
    开始操作group3，选中folder1的图片，点击deep delete， 应该生成一个弹窗，弹窗列出了10张图片的列表(是10张，whitelist的文件也应该被检查出来)
    点击确认删除
    打开Setting页面，找到whitelist的部分，点击refresh按钮
        此时应该有2组，每个组只有2张图片了
    继续操作group3，选中folder3的图片，点击deep delete， 应该生成一个弹窗，弹窗列出了10张图片的列表(是10张，whitelist的文件也应该被检查出来)
    点击确认删除
    打开Setting页面，找到whitelist的部分，点击refresh按钮，
        此时应该是空的
    检查文件系统，
        scan_folder/folder1消失
        scan_folder/folder2还在
        scan_folder/folder3消失
    检查DB
        在phash表里，folder1,folder3的记录应该都没了
        在whitelist表里，所有记录应该都没了
        在duplicate表里，folder1,folder3的记录应该都没了
    清空测试数据，恢复Setting
